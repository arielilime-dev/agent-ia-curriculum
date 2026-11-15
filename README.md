# Resume Analyzer API

Analisador de currículos com IA e API REST completa, escrito em Python com FastAPI e
SQLAlchemy assíncrono. O projeto extrai texto de PDF/DOCX/TXT, estrutura o perfil do
candidato, calcula um score de aderência (com ou sem descrição de vaga), aplica checagens
de ATS e enriquece o resultado com um provedor de IA — com fallback determinístico para
funcionar offline.

> **Status:** pronto para demonstração e como base de produto. 416 testes automatizados,
> 93% de cobertura, lint e formatação verificados com Ruff.

---

## Sumário

- [Principais recursos](#principais-recursos)
- [Stack](#stack)
- [Arquitetura](#arquitetura)
- [Como executar](#como-executar)
- [Testes e qualidade](#testes-e-qualidade)
- [API REST](#api-rest)
- [Exemplos de uso](#exemplos-de-uso)
- [Integração com IA](#integração-com-ia)
- [Configuração](#configuração)
- [Segurança](#segurança)
- [Banco de dados](#banco-de-dados)
- [Docker](#docker)
- [Decisões de projeto](#decisões-de-projeto)
- [Limitações e próximos passos](#limitações-e-próximos-passos)
- [Estrutura de pastas](#estrutura-de-pastas)

---

## Principais recursos

| Área | O que está implementado |
| --- | --- |
| Extração | PDF (`pypdf`), DOCX com tabelas (`python-docx`), TXT e Markdown; detecção de encoding (UTF-8/BOM/UTF-16/CP1252) e limites de tamanho |
| Parsing | Contato (nome, e-mail, telefone, localização, LinkedIn/GitHub), resumo, experiências com datas e empresas, formação com nível, idiomas, certificações, projetos e catálogo de ~100 competências |
| Pontuação | Score 0–100 em 5 dimensões ponderadas (competências, experiência, formação, palavras-chave, ATS), com explicação por dimensão |
| IA | Camada de provedores: `heuristic` (offline), OpenAI, DeepSeek, Ollama e qualquer gateway compatível; retry, timeout, parsing robusto de JSON e fallback automático |
| API | 16 rotas versionadas em `/api/v1`, documentação OpenAPI/Swagger, paginação, filtros e erros com `code` estável |
| Autenticação | JWT HS256 de curta duração + refresh token opaco com rotação, detecção de reuso, logout e revogação em massa |
| Banco | SQLAlchemy 2.0 async, SQLite por padrão e PostgreSQL via `asyncpg`; UUIDs e timestamps UTC |
| Segurança | PBKDF2-HMAC-SHA256 (600k iterações), política de senha, rate limit, limites de upload, proteção contra path traversal, headers de segurança |
| Operação | App factory testável, health/readiness probes, logs com request-id, Docker + Compose, scripts de init/seed |

---

## Stack

- **Python 3.11+** (testado em 3.14)
- **FastAPI** + **Uvicorn**
- **SQLAlchemy 2.0 async** + **aiosqlite** / **asyncpg**
- **Pydantic v2** + **pydantic-settings**
- **httpx** (cliente da IA e testes)
- **pypdf**, **python-docx**
- **pytest**, **pytest-asyncio**, **pytest-cov**, **Ruff**

Autenticação, JWT e hashing de senha usam apenas a biblioteca padrão — sem dependências
frágeis como `passlib`/`bcrypt` (veja [decisões](#decisões-de-projeto)).

---

## Arquitetura

```text
HTTP  ──►  FastAPI (app/api/v1)  ──►  Services (regras de negócio)
                │                        │
                │                        ├──► Storage (arquivos)
                │                        └──► SQLAlchemy (SQLite/PostgreSQL)
                │
                └──► Pipeline do analisador
                         ├── Extractors (PDF/DOCX/TXT)
                         ├── Parser (heurístico PT/EN)
                         ├── Scoring (determinístico)
                         └── AI Provider (LLM ou heurístico) ──► fallback
```

Mais detalhes em [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

---

## Como executar

### 1. Instalar dependências

```bash
python -m pip install -r requirements-dev.txt
```

Ou, em ambiente virtual:

```bash
python -m venv .venv
# Windows (PowerShell)
.venv\Scripts\Activate.ps1
# Linux/macOS
source .venv/bin/activate

pip install -r requirements-dev.txt
```

### 2. Configurar

```bash
cp .env.example .env      # Windows: Copy-Item .env.example .env
```

Para desenvolvimento, os valores padrão funcionam sem edição (a IA fica em modo
`heuristic`, sem chave de API).

### 3. Criar o banco e popular dados de demonstração (opcional)

```bash
python -m scripts.init_db
python -m scripts.seed
```

O seed cria `demo@resumeanalyzer.com.br` / `DemoPass123` com um currículo e uma análise.

> O seed também cria o schema; rodar `init_db` antes é opcional em SQLite.

### 4. Subir a API

```bash
uvicorn app.main:app --reload
```

- API: <http://127.0.0.1:8000>
- Swagger: <http://127.0.0.1:8000/docs>
- ReDoc: <http://127.0.0.1:8000/redoc>
- OpenAPI: <http://127.0.0.1:8000/openapi.json>

Os dados ficam em `data/app.db` e `data/uploads/` (configuráveis).

---

## Testes e qualidade

```bash
pytest -q                            # suíte completa
pytest tests/unit -q                 # apenas unitários
pytest tests/api -q                  # apenas HTTP
pytest --cov=app --cov-report=term-missing
ruff check app tests scripts
ruff format --check app tests scripts
```

Resultado atual:

```text
416 passed in ~21s
coverage: 93%
ruff: All checks passed
```

A suíte cobre **casos positivos, negativos e de borda**:

- **Positivos:** currículo sênior PT-BR e júnior em inglês, PDF/DOCX/TXT, análise com e sem
  vaga, fluxo completo de registro → upload → análise → estatísticas.
- **Negativos:** senha fraca, e-mail duplicado, token expirado/adulterado, usuário inativo,
  arquivo corrompido, extensão não suportada, acesso a recursos de outro usuário (404),
  falha do provedor de IA, JSON inválido do LLM, limite de taxa excedido.
- **Bordas:** arquivo vazio, PDF sem texto, currículo sem seções, currículo mínimo, textos
  com acentos/caracteres de controle, datas sobrepostas, anos sem data, divisão por zero
  evitada, scores sempre entre 0 e 100, paginação vazia.

> Os testes criam diretórios em `.pytest-tmp/` (e não em `tmp_path`) para funcionar em
> pastas sincronizadas pelo OneDrive, onde `tempfile.mkdtemp` pode negar a criação de
> subdiretórios.

---

## API REST

Base: `/api/v1`. Todas as rotas de negócio exigem `Authorization: Bearer <access_token>`,
exceto as marcadas como públicas.

| Método | Rota | Descrição | Auth |
| --- | --- | --- | --- |
| `GET` | `/health`, `/health/live` | Liveness | — |
| `GET` | `/health/ready` | Readiness (testa o banco) | — |
| `POST` | `/auth/register` | Cria conta e devolve tokens | — |
| `POST` | `/auth/login` | Login OAuth2 password (form) | — |
| `POST` | `/auth/refresh` | Rotaciona o refresh token | — |
| `POST` | `/auth/logout` | Revoga um ou todos os refresh tokens | ✅ |
| `GET` | `/users/me` | Perfil atual | ✅ |
| `PATCH` | `/users/me` | Atualiza nome/e-mail | ✅ |
| `POST` | `/users/me/password` | Troca senha e revoga sessões | ✅ |
| `GET` | `/users/me/stats` | Agregados do dashboard | ✅ |
| `DELETE` | `/users/me` | Exclui conta, currículos e arquivos | ✅ |
| `POST` | `/resumes` | Upload multipart (`file`, `title?`) | ✅ |
| `GET` | `/resumes` | Lista com paginação e busca | ✅ |
| `GET` | `/resumes/{id}` | Detalhe + dados estruturados | ✅ |
| `GET` | `/resumes/{id}/text` | Texto extraído | ✅ |
| `DELETE` | `/resumes/{id}` | Remove currículo, arquivo e análises | ✅ |
| `POST` | `/analyses` | Analisa currículo (vaga opcional) | ✅ |
| `GET` | `/analyses` | Lista com filtros `resume_id`/`min_score` | ✅ |
| `GET` | `/analyses/{id}` | Relatório completo | ✅ |
| `DELETE` | `/analyses/{id}` | Remove análise | ✅ |
| `GET` | `/skills` | Catálogo de competências suportadas | ✅ |

Referência completa com payloads e códigos de erro: [docs/API.md](docs/API.md).
Schema OpenAPI exportado: [docs/openapi.json](docs/openapi.json).

### Formato de erro

```json
{
  "detail": "Email already registered",
  "code": "email_already_registered"
}
```

Erros de validação retornam `422` com `code: "validation_error"` e a lista de campos em
`details.errors`.

---

## Exemplos de uso

### Registrar e autenticar

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "ana@example.com",
    "full_name": "Ana Silva",
    "password": "SenhaSegura1"
  }'
```

```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=ana@example.com&password=SenhaSegura1"
```

Resposta (resumida):

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "refresh_token": "Rk3...opaque...",
  "token_type": "bearer",
  "expires_in": 900
}
```

### Upload de currículo

```bash
TOKEN="<access_token>"

curl -X POST http://127.0.0.1:8000/api/v1/resumes \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@curriculo.pdf" \
  -F "title=Currículo Backend 2026"
```

Resposta (resumida):

```json
{
  "id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
  "title": "Currículo Backend 2026",
  "original_filename": "curriculo.pdf",
  "language": "pt",
  "word_count": 312,
  "years_experience": 8.8,
  "education_level": 4,
  "skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
  "parsed": {
    "contact": {
      "full_name": "João da Silva",
      "email": "joao.silva@example.com",
      "linkedin": "linkedin.com/in/joaosilva"
    },
    "experience": [
      {
        "title": "Desenvolvedor Backend Sênior",
        "company": "Tech Corp",
        "start_date": "2021-01",
        "end_date": null,
        "is_current": true,
        "months": 71
      }
    ]
  }
}
```

### Analisar contra uma vaga

```bash
curl -X POST http://127.0.0.1:8000/api/v1/analyses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "resume_id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
    "job_title": "Desenvolvedor Backend Sênior",
    "job_description": "Requisitos: 5+ anos com Python e FastAPI, PostgreSQL, Docker, Kubernetes, AWS."
  }'
```

Resposta (resumida):

```json
{
  "overall_score": 90.6,
  "verdict": "excellent",
  "breakdown": {
    "skills":     {"label": "Competências", "score": 100.0, "weight": 0.4, "weighted": 40.0, "reason": "7 de 7 competências da vaga"},
    "experience": {"label": "Experiência", "score": 100.0, "weight": 0.25, "weighted": 25.0, "reason": "8.8 de 5 anos exigidos"},
    "education":  {"label": "Formação", "score": 85.0, "weight": 0.1, "weighted": 8.5},
    "keywords":   {"label": "Palavras-chave", "score": 86.7, "weight": 0.15, "weighted": 13.0},
    "ats":        {"label": "Compatibilidade com ATS", "score": 87.5, "weight": 0.1, "weighted": 8.75}
  },
  "matched_skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
  "missing_skills": [],
  "strengths": ["8.8 anos de experiência profissional comprovada", "..."],
  "suggestions": ["Adicione LinkedIn ou GitHub ao cabeçalho."],
  "ats_checks": [
    {"id": "email", "label": "E-mail de contato", "passed": true, "hint": "Inclua um e-mail profissional no cabeçalho do currículo."}
  ],
  "ai_provider": "heuristic",
  "ai_model": "rules-v1",
  "ai_degraded": false,
  "duration_ms": 18
}
```

### Paginação e filtros

```bash
curl "http://127.0.0.1:8000/api/v1/analyses?page=1&page_size=20&min_score=70" \
  -H "Authorization: Bearer $TOKEN"
```

```json
{"items": [], "total": 0, "page": 1, "page_size": 20, "pages": 0}
```

---

## Integração com IA

O analisador sempre calcula o resultado determinístico. A IA **enriquece** o parecer com
resumo, pontos fortes e melhorias — sem poder alterar o score calculado.

```text
AI_PROVIDER=heuristic   # padrão: offline, determinístico, sem custo
AI_PROVIDER=openai      # api.openai.com    (requer AI_API_KEY)
AI_PROVIDER=deepseek    # api.deepseek.com  (requer AI_API_KEY)
AI_PROVIDER=ollama      # localhost:11434   (não exige chave)
AI_PROVIDER=openai_compatible  # qualquer gateway; defina AI_BASE_URL + AI_API_KEY
```

Para OpenAI:

```bash
AI_PROVIDER=openai
AI_API_KEY=sk-...
AI_MODEL=gpt-4o-mini
AI_FALLBACK_ENABLED=true
```

Se o provedor falhar (timeout, 429, 5xx, JSON inválido), o `FallbackProvider` usa o
analisador heurístico e marca a resposta com `ai_degraded: true` — a análise nunca é
perdida. Detalhes e prompts em `app/analyzer/ai/`.

---

## Configuração

Variáveis principais (todas com padrão seguro para desenvolvimento — veja `.env.example`):

| Variável | Padrão | Descrição |
| --- | --- | --- |
| `ENVIRONMENT` | `development` | `development`, `test` ou `production` (ativa hardening) |
| `DATABASE_URL` | `sqlite+aiosqlite:///./data/app.db` | URL assíncrona do banco |
| `JWT_SECRET_KEY` | segredo de dev | **obrigatório trocar** em produção (≥ 32 chars) |
| `ACCESS_TOKEN_TTL_MINUTES` | `15` | Validade do access token |
| `REFRESH_TOKEN_TTL_DAYS` | `7` | Validade do refresh token |
| `PASSWORD_HASH_ITERATIONS` | `600000` | Custo do PBKDF2 (mín. 100k em produção) |
| `MAX_UPLOAD_BYTES` | `5242880` | Limite de upload (5 MiB) |
| `MAX_RESUME_CHARS` | `100000` | Texto extraído máximo |
| `STORAGE_DIR` | `./data/uploads` | Diretório dos arquivos originais |
| `ALLOWED_EXTENSIONS` | `[".pdf",".docx",".txt",".md"]` | JSON array |
| `AI_PROVIDER` / `AI_API_KEY` / `AI_MODEL` | `heuristic` / — / `gpt-4o-mini` | Configuração da IA |
| `AI_TIMEOUT_SECONDS` / `AI_MAX_RETRIES` | `30` / `2` | Resiliência do provedor |
| `CORS_ORIGINS` | `["http://localhost:3000"]` | JSON array |
| `RATE_LIMIT_ENABLED` | `true` | Rate limit nos endpoints de auth |
| `RATE_LIMIT_AUTH_PER_MINUTE` | `30` | Tentativas por IP/minuto |

---

## Segurança

- **Senhas:** PBKDF2-HMAC-SHA256 com salt aleatório de 16 bytes, 600k iterações,
  comparação em tempo constante e rehash transparente. Política mínima de 8 caracteres,
  maiúscula, minúscula, dígito e blocklist.
- **Access token:** JWT HS256 com `iss`, `iat`, `exp`, `jti` e `type`; validação de
  assinatura em tempo constante, algoritmo allow-list e leeway configurável.
- **Refresh token:** opaco (48 bytes aleatórios), apenas o SHA-256 é persistido; rotação a
  cada uso e **detecção de reuso** — um token reutilizado revoga todas as sessões do usuário.
- **Uploads:** validação por extensão e tamanho, extração em thread separada, nomes
  sanitizados e chaves de armazenamento validadas contra path traversal.
- **Isolamento:** toda consulta filtra por `user_id`; recursos de terceiros retornam `404`
  (sem vazar existência).
- **HTTP:** rate limit por IP na autenticação, CORS explícito, `X-Content-Type-Options`,
  `X-Frame-Options`, `Referrer-Policy`, `Cache-Control: no-store` e `X-Request-ID`.
- **Produção:** a aplicação se recusa a iniciar com segredo padrão/curto, iterações baixas,
  `DEBUG=true` ou CORS `*`.

> Para produção real, adicione HTTPS no proxy reverso, rate limit distribuído (Redis),
> backups e rotação de segredos.

---

## Banco de dados

Modelo relacional:

```text
users 1 ─── N resumes 1 ─── N analyses
  │
  └── 1 ─── N refresh_tokens
```

- `users`: e-mail único, hash de senha, flags e último login.
- `refresh_tokens`: hash do token, expiração, revogação e metadados (IP/user-agent).
- `resumes`: metadados do arquivo, texto extraído, hash, idioma, competências e JSON
  estruturado do perfil.
- `analyses`: score, veredito, breakdown, competências/palavras-chave, sugestões, checagens
  de ATS, provider/modelo de IA e duração.

SQLite é o padrão. Para PostgreSQL:

```bash
pip install ".[postgres]"
export DATABASE_URL="postgresql+asyncpg://postgres:postgres@localhost:5432/resume_analyzer"
python -m scripts.init_db
```

O schema é criado de forma idempotente por `create_all` (e pelo lifespan da aplicação). Para
evolução controlada em produção, use Alembic (ver limitações).

---

## Docker

```bash
export JWT_SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(64))')"
docker compose up --build
```

A stack sobe a API em <http://localhost:8000> e PostgreSQL 16. O volume `uploads` guarda os
arquivos e `pgdata` o banco.

---

## Decisões de projeto

- **Biblioteca padrão para JWT e hashing.** Evita dependências nativas (bcrypt/passlib)
  problemáticas em Python 3.14 e reduz a superfície de ataque (algoritmo fixo, sem
  `alg: none`). O formato do hash é auto-descritivo, permitindo upgrade de parâmetros.
- **Async de ponta a ponta.** SQLAlchemy 2.0 assíncrono + aiosqlite/asyncpg; parsing e
  hashing rodam em `asyncio.to_thread` para não bloquear o event loop.
- **Determinístico primeiro, IA depois.** O score é auditável e reproduzível; a IA só
  adiciona narrativa. Isso permite testar a lógica sem chamadas externas e operar offline.
- **Fallback explícito.** Falha de LLM degrada a experiência (`ai_degraded`) em vez de
  derrubar a requisição.
- **Isolamento de recursos por `user_id` + 404.** Não revela a existência de dados de
  terceiros.
- **App factory.** `create_app(settings)` permite instanciar ambientes isolados nos testes
  sem poluir o banco de desenvolvimento.
- **Contratos com Pydantic.** Validação de entrada/saída e OpenAPI sempre sincronizado.

---

## Limitações e próximos passos

- O rate limiter é em memória (por processo). Em múltiplas réplicas, migrar para Redis.
- O schema usa `create_all`; para produção com migrações versionadas, adotar Alembic.
- PDFs escaneados (imagem) não têm OCR — o upload retorna `empty_document`. Próximo passo:
  OCR opcional com Tesseract.
- O parser é heurístico para PT-BR/inglês; currículos muito não convencionais podem ter
  baixa extração de seções.
- A IA usa um único prompt de enriquecimento; melhorias futuras: embeddings para
  similaridade semântica, extração de requisitos estruturada e análise em lote assíncrona.
- Não há verificação de e-mail nem recuperação de senha (fora do escopo desta entrega).

---

## Estrutura de pastas

```text
resume-analyzer/
├── app/
│   ├── main.py                  # app factory, middlewares, handlers
│   ├── core/                    # config, segurança, erros, logging, rate limit, paginação
│   ├── db/                      # base, modelos ORM, engine/sessão assíncrona
│   ├── schemas/                 # contratos Pydantic (auth, user, resume, analysis)
│   ├── services/                # regras de negócio (auth, usuários, currículos, análises, storage)
│   ├── analyzer/
│   │   ├── text.py              # normalização, keywords, contato, idioma
│   │   ├── extractors.py        # PDF/DOCX/TXT/MD → texto
│   │   ├── parser.py            # texto → perfil estruturado
│   │   ├── skills.py            # catálogo e matching de competências
│   │   ├── education.py         # níveis de formação
│   │   ├── scoring.py           # score ponderado + ATS + narrativa
│   │   ├── pipeline.py          # parse → score → IA → merge
│   │   └── ai/                  # base, prompts, heuristic, openai_compatible, fallback, factory
│   └── api/
│       ├── deps.py              # dependências (auth, sessão, settings)
│       ├── middleware.py        # request-id, logs, headers
│       ├── router.py
│       └── v1/                  # auth, users, resumes, analyses, health, meta
├── tests/
│   ├── conftest.py              # fixtures isoladas
│   ├── factories.py             # builders de currículos/PDF/DOCX
│   ├── unit/                    # 316 testes
│   └── api/                     # 100 testes HTTP
├── scripts/
│   ├── init_db.py
│   └── seed.py
├── docs/
│   ├── API.md
│   ├── ARCHITECTURE.md
│   └── openapi.json
├── pyproject.toml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── README.md
```

---

## Licença

MIT. Veja [LICENSE](LICENSE).
