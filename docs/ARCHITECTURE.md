# Arquitetura

Este documento descreve as decisões estruturais do Resume Analyzer, o fluxo de uma
requisição, o modelo de dados, a fórmula de pontuação e a estratégia de testes.

---

## 1. Objetivos

1. **Análise reproduzível:** o score precisa ser determinístico e auditável, mesmo com IA.
2. **Funcionar offline:** sem chave de API, o produto continua útil (provedor heurístico).
3. **Falhar de forma segura:** LLM indisponível degrada o parecer, não a disponibilidade.
4. **Isolamento de dados:** nenhum usuário acessa currículos/análises de outro.
5. **Testabilidade:** a aplicação é montada por uma factory, com banco e storage isolados.

Não objetivos desta versão: OCR, recrutamento colaborativo, multi-tenant por organização,
busca semântica com embeddings e filas de processamento.

---

## 2. Camadas

```text
┌────────────────────────────────────────────────────────────────────┐
│  app/api/v1          Rotas HTTP, validação de entrada, status codes │
├────────────────────────────────────────────────────────────────────┤
│  app/services        Casos de uso, transações, autorização          │
├────────────────────────────────────────────────────────────────────┤
│  app/db              Modelos SQLAlchemy, sessão assíncrona           │
│  app/services/storage Armazenamento de arquivos (filesystem)         │
├────────────────────────────────────────────────────────────────────┤
│  app/analyzer        Domínio puro: texto, parsing, score, IA         │
├────────────────────────────────────────────────────────────────────┤
│  app/core            Config, segurança, erros, logging, paginação    │
└────────────────────────────────────────────────────────────────────┘
```

Regras de dependência:

- `analyzer` **não** importa FastAPI nem SQLAlchemy (domínio testável isoladamente).
- Rotas **não** acessam o banco diretamente: sempre passam por um service.
- `core` é transversal e não depende de `api`/`services`.
- `schemas` são contratos de borda; o domínio usa dataclasses.

---

## 3. Ciclo de vida de uma requisição

```text
Cliente
  │  POST /api/v1/analyses  (Bearer JWT)
  ▼
RequestContextMiddleware
  ├─ gera/propaga X-Request-ID
  ├─ mede duração
  └─ adiciona headers de segurança
  ▼
FastAPI routing + dependências
  ├─ get_current_user → decode JWT → carrega User
  ├─ get_session      → AsyncSession (rollback em exceção)
  └─ get_pipeline     → ResumeAnalysisPipeline (app.state)
  ▼
analysis_service.create_analysis
  ├─ valida posse do currículo (user_id + id)
  ├─ pipeline.analyze(texto, vaga)
  │    ├─ ResumeParser.parse
  │    ├─ score_resume
  │    └─ AI provider (LLM) ─ falha ─► heurístico + degraded
  ├─ persiste Analysis
  └─ commit + refresh
  ▼
Response model (Pydantic) → JSON
```

O `lifespan` cria as tabelas (quando habilitado) e libera engine/cliente HTTP no shutdown.
Nos testes, `initialize_database(app)` executa o mesmo bootstrap sem depender do lifespan,
já que o `ASGITransport` do httpx não o dispara.

---

## 4. Modelo de dados

```text
┌──────────────────────┐        ┌──────────────────────────┐
│ users                │ 1    N │ refresh_tokens           │
│----------------------│────────│--------------------------│
│ id (uuid, pk)        │        │ id (uuid, pk)            │
│ email (unique)       │        │ user_id (fk, cascade)    │
│ full_name            │        │ token_hash (sha256, uq)  │
│ hashed_password      │        │ expires_at, revoked_at   │
│ is_active            │        │ user_agent, ip_address    │
│ is_superuser         │        └──────────────────────────┘
│ last_login_at        │
│ created_at/updated_at│        ┌──────────────────────────┐
└──────────┬───────────┘ 1    N │ resumes                  │
           │                    │--------------------------│
           ├────────────────────│ id, user_id (fk)         │
           │                    │ title, original_filename │
           │                    │ content_type, size_bytes │
           │                    │ storage_key (unique)     │
           │                    │ text, text_sha256        │
           │                    │ language, word_count     │
           │                    │ years_experience         │
           │                    │ education_level          │
           │                    │ skills (JSON)            │
           │                    │ parsed (JSON)            │
           │                    └──────────┬───────────────┘
           │                               │ 1
           │                               │ N
           │                    ┌──────────▼───────────────┐
           └────────────────────│ analyses                 │
                                │--------------------------│
                                │ id, user_id, resume_id   │
                                │ job_title, job_description│
                                │ overall_score, verdict   │
                                │ breakdown (JSON)         │
                                │ matched/missing skills   │
                                │ matched/missing keywords │
                                │ strengths/suggestions    │
                                │ ats_checks (JSON)        │
                                │ summary                  │
                                │ ai_provider/model/degraded│
                                │ duration_ms              │
                                └──────────────────────────┘
```

Decisões:

- **UUID em string**: portável entre SQLite e PostgreSQL, seguro para exposição em URLs.
- **`UTCDateTime`**: normaliza para UTC naive no banco e devolve `tzinfo=UTC` na leitura,
  evitando comparações ingênuas com `now()`.
- **JSON denormalizado**: `parsed`, `breakdown` e `skills` são snapshots imutáveis do momento
  da análise; mudanças futuras no parser não reescrevem históricos.
- **Cascade**: deletar usuário/currículo remove dependentes (FK `ON DELETE CASCADE` no
  SQLite via `PRAGMA foreign_keys=ON`, além de deletes explícitos nos services).

---

## 5. Pipeline do analisador

```text
bytes ──► extractors.extract_text ──► texto limpo
                                        │
                                        ▼
                              parser.parse(text) ──► ParsedResume
                                        │
                                        ▼
                         scoring.score_resume(parsed, vaga) ──► resultado determinístico
                                        │
                                        ▼
                         AIProvider.analyze(context) ──► AIInsight
                                        │
                                        ▼
                              merge (resumo/pontos/melhorias)
                                        │
                                        ▼
                                   AnalysisOutcome
```

### 5.1 Extração

- Extensão allow-list: `.pdf`, `.docx`, `.txt`, `.md`.
- Limite de 50 páginas de PDF e 100k caracteres de texto.
- PDFs criptografados ou corrompidos → `CorruptedDocumentError` (HTTP 422).
- PDFs sem texto (escaneados) → `EmptyDocumentError` (HTTP 422).
- DOCX inclui tabelas (com deduplicação de células mescladas).
- Texto: tenta UTF-8/BOM, UTF-16, CP1252 e, por fim, Latin-1.

### 5.2 Parsing

Heurísticas independentes de idioma (PT-BR/inglês):

- cabeçalhos de seção normalizados (sem acento, minúsculos) e dicionário de sinônimos;
- nome a partir do preâmbulo, ignorando títulos de cargo, contatos e cabeçalhos;
- datas em `MM/AAAA`, `jan 2020`, `2020`, `Atual/Present`; intervalos sobrepostos são
  mesclados antes de somar meses;
- formação classificada em 0–7 (fundamental → doutorado);
- competências via catálogo com aliases (`Postgres` → PostgreSQL, `k8s` → Kubernetes),
  com limites de palavra para evitar `java` dentro de `javascript`.

### 5.3 Pontuação

```text
score = 0.40·skills + 0.25·experience + 0.10·education + 0.15·keywords + 0.10·ats
```

| Dimensão | Com descrição de vaga | Sem descrição de vaga |
| --- | --- | --- |
| `skills` | cobertura das competências exigidas | amplitude técnica (quantidade + diversidade de categorias) |
| `experience` | `min(anos / anos_exigidos, 1)` | `min(anos / 8, 1)` |
| `education` | 100 se atende; −25 por nível faltante | mapa fixo por nível (10–100) |
| `keywords` | cobertura de keywords da vaga | qualidade: verbos de ação, métricas, resumo |
| `ats` | 8 checagens estruturais (e-mail, telefone, tamanho, seções, links) | idem |

Veredito: `excellent ≥ 85`, `strong ≥ 70`, `fair ≥ 55`, `weak < 55`.

Cada dimensão retorna `score`, `weight`, `weighted`, `label`, `reason` e `details`, o que
permite explicar o resultado ao usuário e testar a aritmética.

### 5.4 IA

Contrato (`app/analyzer/ai/base.py`):

```python
class AIProvider(Protocol):
    name: str
    model: str
    async def analyze(self, context: AnalysisContext) -> AIInsight: ...
```

- **HeuristicProvider**: monta o insight a partir do resultado determinístico. Confiança
  0.55 quando há conteúdo, 0.2 para currículo vazio.
- **OpenAICompatibleProvider**: `POST {base_url}/chat/completions`, `response_format=json_object`,
  timeout, até `AI_MAX_RETRIES` tentativas com backoff `0.5, 1.0, ...` (máx. 5s) para
  408/429/5xx/timeouts. Erros 4xx não são repetidos.
- **FallbackProvider**: captura `AIProviderError` e qualquer exceção inesperada, executa o
  heurístico e marca `ai_degraded=true`, `ai_provider="<primário>->fallback"`.
- **Pipeline**: se o provedor configurado falhar mesmo após o fallback, usa o heurístico
  diretamente. A análise nunca falha por causa da IA.

Parsing da resposta do LLM:

1. remove cercas markdown;
2. localiza o primeiro `{` e o último `}`;
3. valida JSON e tipos;
4. limita listas (6 itens) e resumo (1200 chars);
5. faz clamp da confiança em `[0, 1]`.

O score determinístico **não** é substituído pela IA; apenas resumo, pontos fortes e
melhorias são mesclados (com deduplicação e limites).

---

## 6. Segurança

### Tokens

```text
access  = JWT HS256 {sub, iss, type=access, iat, exp, jti}   TTL 15 min
refresh = secrets.token_urlsafe(48)  ──sha256──►  refresh_tokens.token_hash   TTL 7 dias
```

- O refresh token nunca é persistido em claro.
- Rotação: cada refresh revoga o anterior e emite um novo.
- Reuso de token já rotacionado é tratado como roubo: **todas** as sessões do usuário são
  revogadas e a requisição falha com `refresh_token_reused`.
- Troca de senha revoga todas as sessões.
- Logout aceita um token específico ou revoga todas as sessões.

### Senhas

Formato: `pbkdf2_sha256$<iterações>$<salt_b64>$<digest_b64>`, salt de 16 bytes e 32 bytes
de digest. A comparação usa `hmac.compare_digest`; parâmetros antigos são detectados por
`password_needs_rehash`.

### Uploads

- Limite aplicado antes e depois da leitura do multipart.
- Nome saneado (`Path.name`, remoção de caracteres de controle).
- Chave `user_id/uuid.ext`; qualquer tentativa de `..`, caminho absoluto ou unidade Windows
  é rejeitada por `Storage._resolve`.
- Escrita atômica (arquivo temporário + `os.replace`) e limpeza em caso de falha.

### Erros

`AppError` carrega `status_code`, `code`, `details` e headers. O handler global devolve:

```json
{"detail": "...", "code": "..."}
```

Erros de validação retornam `422` com `code=validation_error` e `details.errors`.
Recursos de outros usuários retornam `404`, não `403`, para não revelar existência.

---

## 7. Concorrência e desempenho

- Endpoints e banco são assíncronos (`AsyncSession`); PBKDF2 e parsing rodam em
  `asyncio.to_thread`, liberando o event loop.
- `expire_on_commit=False` evita I/O implícito após o commit.
- SQLite usa WAL e `PRAGMA foreign_keys=ON`; PostgreSQL usa `pool_pre_ping`.
- Listagens são paginadas (máx. 100) e ordenadas por `created_at, id` para estabilidade.
- `skills` é calculado por regex sobre o texto normalizado (~100 padrões); o custo é linear
  no tamanho do texto, limitado a 100k caracteres.

Gargalos esperados em escala: chamadas ao LLM (latência) e armazenamento local de arquivos.
Próximos passos naturais: fila assíncrona para análises em lote, cache de embeddings e
storage S3-compatível.

---

## 8. Observabilidade

- `RequestContextMiddleware` injeta `X-Request-ID` (aceita o do cliente), mede duração,
  registra método/rota/status e adiciona `X-Process-Time-Ms`.
- Logs usam o request-id no formato `%(request_id)s`.
- `/health/live` não toca dependências; `/health/ready` executa `SELECT 1`.
- Falhas de IA são logadas com `warning` (degradação) ou `exception` (erro inesperado).

---

## 9. Estratégia de testes

| Camada | Arquivos | Foco |
| --- | --- | --- |
| Segurança | `test_security.py` | hashing, política, JWT adulterado/expirado, refresh tokens |
| Texto | `test_text.py` | normalização, keywords, contato, telefone, URLs, idioma |
| Extração | `test_extractors.py` | encodings, PDF válido/vazio/corrompido, DOCX com tabela, sanitização |
| Parsing | `test_parser.py` | PT/EN, datas, sobreposição, formação, seções, casos vazios |
| Competências | `test_skills.py` | sinônimos, limites de palavra, categorias |
| Score | `test_scoring.py` | matemática por dimensão, requisitos, ATS, veredito |
| IA | `test_ai.py` | parsing de JSON, retries, timeout, 401, fallback, factory |
| Pipeline | `test_pipeline.py` | merge, degradação, vazio, vaga |
| Storage | `test_storage.py` | atomicidade, path traversal, extensões |
| Rate limit | `test_rate_limit.py` | janela deslizante com relógio falso |
| Config | `test_config.py` | defaults e hardening de produção |
| HTTP | `tests/api/*` | auth, refresh/reuso, isolamento, uploads, análises, stats, docs |

Fixtures:

- `temp_dir` cria diretórios sob `.pytest-tmp/` (evita o problema de ACL do OneDrive).
- `settings_factory` permite sobrescrever qualquer configuração por teste.
- `app`/`client` montam a aplicação com `create_app` + `initialize_database`, sem lifespan.
- `make_client` cria apps adicionais (ex.: rate limit com limites baixos).

---

## 10. Evolução

1. Alembic com migração inicial e CI executando upgrade/downgrade.
2. Rate limit com Redis e idempotência em uploads.
3. OCR opcional e suporte a `.doc`/`.rtf`.
4. Extração estruturada de requisitos da vaga (must-have vs nice-to-have).
5. Embeddings para similaridade semântica e ranking de candidatos.
6. Fila (Celery/RQ/Arq) para análise em lote e webhooks.
