# Referência da API

Base URL local: `http://127.0.0.1:8000`
Prefixo versionado: `/api/v1`
OpenAPI: `GET /openapi.json` · Swagger: `/docs` · ReDoc: `/redoc`

---

## Convenções

- **JSON** em requisições/respostas, exceto upload (`multipart/form-data`) e login
  (`application/x-www-form-urlencoded`).
- **IDs** são UUIDs em string.
- **Datas** são ISO 8601 em UTC (`2026-11-15T23:05:03Z`).
- **Autenticação**: `Authorization: Bearer <access_token>`.
- **Paginação**: `?page=1&page_size=20` (máx. 100). Resposta:

```json
{
  "items": [],
  "total": 0,
  "page": 1,
  "page_size": 20,
  "pages": 0
}
```

- **Erros**: envelope estável com `detail` e `code`; validações incluem `details.errors`.

```json
{
  "detail": "Email already registered",
  "code": "email_already_registered"
}
```

### Códigos de erro

| HTTP | `code` | Quando ocorre |
| --- | --- | --- |
| 401 | `not_authenticated` | Header `Authorization` ausente |
| 401 | `invalid_token` | JWT inválido, expirado ou de usuário inexistente |
| 401 | `invalid_credentials` | E-mail/senha incorretos |
| 401 | `invalid_refresh_token` | Refresh token desconhecido |
| 401 | `refresh_token_expired` | Refresh token vencido |
| 401 | `refresh_token_reused` | Token já rotacionado (todas as sessões são revogadas) |
| 403 | `account_disabled` | Usuário inativo |
| 404 | `resume_not_found` | Currículo inexistente ou de outro usuário |
| 404 | `analysis_not_found` | Análise inexistente ou de outro usuário |
| 404 | `not_found` | Rota/recurso genérico |
| 409 | `email_already_registered` | E-mail já cadastrado |
| 409 | `conflict` | Conflito de integridade no banco |
| 413 | `file_too_large` | Upload acima do limite |
| 415 | `unsupported_file_type` | Extensão fora de `.pdf/.docx/.txt/.md` |
| 422 | `validation_error` | Corpo/params inválidos (Pydantic) |
| 422 | `weak_password` | Senha fora da política (`details.problems`) |
| 422 | `invalid_current_password` | Senha atual incorreta |
| 422 | `password_unchanged` | Nova senha igual à atual |
| 422 | `invalid_password` | Senha incorreta na exclusão de conta |
| 422 | `empty_file` | Upload sem conteúdo |
| 422 | `empty_document` | Documento sem texto extraível |
| 422 | `invalid_document` | PDF/DOCX corrompido ou criptografado |
| 429 | `rate_limited` | Limite de tentativas de autenticação (`Retry-After`) |
| 503 | `database_unavailable` | Readiness sem banco |
| 500 | `internal_error` | Erro inesperado (sem vazamento de stack) |

---

## Autenticação

### `POST /auth/register` — público

Cria a conta e já devolve os tokens.

**Body**

```json
{
  "email": "ana@example.com",
  "full_name": "Ana Silva",
  "password": "SenhaSegura1"
}
```

**Regras**

- e-mail válido e único (comparação case-insensitive);
- `full_name` entre 2 e 120 caracteres;
- senha entre 8 e 128 caracteres, com maiúscula, minúscula e dígito, fora da blocklist de
  senhas comuns.

**201 Created**

```json
{
  "user": {
    "id": "4d00c3b0-b169-459f-99b4-b02648038e45",
    "email": "ana@example.com",
    "full_name": "Ana Silva",
    "is_active": true,
    "is_superuser": false,
    "created_at": "2026-11-15T23:05:03Z",
    "last_login_at": null
  },
  "tokens": {
    "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
    "refresh_token": "Rk3...opaque...",
    "token_type": "bearer",
    "expires_in": 900
  }
}
```

**Erros**: `409 email_already_registered`, `422 validation_error`, `422 weak_password`,
`429 rate_limited`.

---

### `POST /auth/login` — público

OAuth2 password flow. **`username` recebe o e-mail.**

**Form** (`application/x-www-form-urlencoded`)

```text
username=ana@example.com&password=SenhaSegura1
```

**200 OK**

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "token_type": "bearer",
  "expires_in": 900
}
```

**Erros**: `401 invalid_credentials`, `403 account_disabled`, `429 rate_limited`.

---

### `POST /auth/refresh` — público

Rotaciona o refresh token (o antigo é revogado).

**Body**

```json
{"refresh_token": "Rk3...opaque..."}
```

**200 OK**: mesmo formato do login.

**Erros**: `401 invalid_refresh_token`, `401 refresh_token_expired`,
`401 refresh_token_reused` (revoga todas as sessões).

---

### `POST /auth/logout` — autenticado

Revoga um refresh token específico; sem corpo, revoga todas as sessões do usuário.

**Body (opcional)**

```json
{"refresh_token": "Rk3...opaque..."}
```

**204 No Content**. Erros: `401 not_authenticated`, `401 invalid_token`.

---

## Usuários

### `GET /users/me`

**200 OK** — objeto `UserRead`.

---

### `PATCH /users/me`

Atualiza nome e/ou e-mail.

```json
{"full_name": "Ana Souza", "email": "ana.souza@example.com"}
```

**200 OK** — usuário atualizado.
**Erros**: `409 email_already_registered`, `422 validation_error`.

---

### `POST /users/me/password`

Troca a senha e revoga todos os refresh tokens.

```json
{"current_password": "SenhaSegura1", "new_password": "NovaSenhaForte2"}
```

**204 No Content**.
**Erros**: `422 invalid_current_password`, `422 password_unchanged`, `422 weak_password`.

---

### `GET /users/me/stats`

Agregados do dashboard.

```json
{
  "total_resumes": 2,
  "total_analyses": 3,
  "average_score": 82.6,
  "best_score": 90.6,
  "top_skills": [{"skill": "Python", "count": 2}, {"skill": "Docker", "count": 2}],
  "recent_analyses": [
    {
      "id": "08a2345f-1fc4-4b87-b4b4-4e17882dfebd",
      "resume_id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
      "job_title": "Desenvolvedor Backend",
      "overall_score": 78.9,
      "verdict": "strong",
      "ai_provider": "heuristic",
      "ai_degraded": false,
      "created_at": "2026-11-15T23:06:12Z"
    }
  ]
}
```

Se não houver análises, `average_score` e `best_score` são `null`.

---

### `DELETE /users/me`

Exclui a conta, currículos, análises, tokens e arquivos armazenados.

```json
{"password": "SenhaSegura1"}
```

**204 No Content**. Erros: `422 invalid_password`.

---

## Currículos

### `POST /resumes` — multipart

| Campo | Tipo | Obrigatório | Descrição |
| --- | --- | --- | --- |
| `file` | arquivo | sim | `.pdf`, `.docx`, `.txt` ou `.md` |
| `title` | texto | não | Título amigável (padrão: nome do arquivo) |

```bash
curl -X POST http://127.0.0.1:8000/api/v1/resumes \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@curriculo.pdf" \
  -F "title=Currículo 2026"
```

**201 Created**

```json
{
  "id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
  "title": "Currículo 2026",
  "original_filename": "curriculo.pdf",
  "content_type": "application/pdf",
  "size_bytes": 48213,
  "language": "pt",
  "word_count": 312,
  "years_experience": 8.8,
  "education_level": 4,
  "skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
  "parsed": {
    "contact": {
      "full_name": "João da Silva",
      "email": "joao.silva@example.com",
      "phone": "(11) 98765-4321",
      "location": "São Paulo - SP",
      "links": {
        "linkedin": "linkedin.com/in/joaosilva",
        "github": "github.com/joaosilva"
      }
    },
    "summary": "Desenvolvedor backend com 8 anos de experiência...",
    "skills": ["AWS", "Docker", "FastAPI"],
    "education": [
      {
        "degree": "Bacharelado em Ciência da Computação",
        "institution": "Universidade de São Paulo",
        "year": "2014-2017",
        "level": 4
      }
    ],
    "experience": [
      {
        "title": "Desenvolvedor Backend Sênior",
        "company": "Tech Corp",
        "start_date": "2021-01",
        "end_date": null,
        "is_current": true,
        "description": "Desenvolvi APIs REST com Python e FastAPI...",
        "months": 71
      }
    ],
    "languages": [{"name": "Português", "level": "Nativo"}],
    "certifications": [],
    "projects": [],
    "metadata": {
      "word_count": 312,
      "char_count": 2104,
      "language": "pt",
      "sections_found": ["summary", "experience", "education", "skills", "languages"],
      "years_experience": 8.8,
      "education_level": 4
    }
  },
  "created_at": "2026-11-15T23:05:43Z",
  "updated_at": "2026-11-15T23:05:43Z"
}
```

**Erros**: `413 file_too_large`, `415 unsupported_file_type`, `422 empty_file`,
`422 empty_document`, `422 invalid_document`.

> `education_level`: 0 não informado · 1 fundamental · 2 médio · 3 técnico · 4 superior ·
> 5 pós/MBA · 6 mestrado · 7 doutorado.

---

### `GET /resumes`

Query: `page`, `page_size`, `search` (título, máx. 100).

```json
{
  "items": [
    {
      "id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
      "title": "Currículo 2026",
      "language": "pt",
      "word_count": 312,
      "years_experience": 8.8,
      "education_level": 4,
      "skills": ["AWS", "Docker"],
      "created_at": "2026-11-15T23:05:43Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

### `GET /resumes/{resume_id}`

**200 OK** — mesmo payload do upload.
**Erros**: `404 resume_not_found`.

---

### `GET /resumes/{resume_id}/text`

```json
{
  "id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
  "text": "João da Silva\nDesenvolvedor Backend Sênior...",
  "word_count": 312
}
```

---

### `DELETE /resumes/{resume_id}`

Remove o currículo, o arquivo e **todas as análises** associadas.

**204 No Content**. Erros: `404 resume_not_found`.

---

## Análises

### `POST /analyses`

```json
{
  "resume_id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
  "job_title": "Desenvolvedor Backend Sênior",
  "job_description": "Requisitos: 5+ anos com Python e FastAPI, PostgreSQL, Docker, Kubernetes e AWS."
}
```

`job_title` e `job_description` são opcionais. Sem vaga, o score usa modo geral.
`job_description` aceita até 20.000 caracteres.

**201 Created**

```json
{
  "id": "08a2345f-1fc4-4b87-b4b4-4e17882dfebd",
  "resume_id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
  "job_title": "Desenvolvedor Backend Sênior",
  "job_description": "Requisitos: 5+ anos com Python...",
  "overall_score": 90.6,
  "verdict": "excellent",
  "breakdown": {
    "skills": {
      "label": "Competências",
      "score": 100.0,
      "weight": 0.4,
      "weighted": 40.0,
      "reason": "7 de 7 competências da vaga",
      "details": {
        "required_skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
        "matched_skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
        "missing_skills": [],
        "coverage": 1.0
      }
    },
    "experience": {
      "label": "Experiência",
      "score": 100.0,
      "weight": 0.25,
      "weighted": 25.0,
      "reason": "8.8 de 5 anos exigidos",
      "details": {"years": 8.8, "required_years": 5}
    },
    "education": {
      "label": "Formação",
      "score": 85.0,
      "weight": 0.1,
      "weighted": 8.5,
      "reason": "Ensino superior",
      "details": {
        "level": 4,
        "label": "Ensino superior",
        "required_level": null,
        "required_label": null
      }
    },
    "keywords": {
      "label": "Palavras-chave",
      "score": 86.7,
      "weight": 0.15,
      "weighted": 13.0,
      "reason": "13 de 15 palavras-chave da vaga"
    },
    "ats": {
      "label": "Compatibilidade com ATS",
      "score": 87.5,
      "weight": 0.1,
      "weighted": 8.75,
      "reason": "7 de 8 verificações aprovadas"
    }
  },
  "matched_skills": ["AWS", "Docker", "FastAPI", "Kubernetes", "PostgreSQL", "Python"],
  "missing_skills": [],
  "matched_keywords": ["python", "fastapi", "postgresql", "docker"],
  "missing_keywords": ["kubernetes", "aws"],
  "strengths": [
    "Atende 6 competência(s) exigida(s): AWS, Docker, FastAPI, Kubernetes, PostgreSQL, Python",
    "8.8 anos de experiência profissional comprovada",
    "Formação acadêmica: ensino superior"
  ],
  "suggestions": ["Adicione LinkedIn ou GitHub ao cabeçalho."],
  "ats_checks": [
    {
      "id": "email",
      "label": "E-mail de contato",
      "passed": true,
      "hint": "Inclua um e-mail profissional no cabeçalho do currículo."
    }
  ],
  "summary": "Perfil com 8.8 anos de experiência profissional; 10 competências identificadas...",
  "ai_provider": "heuristic",
  "ai_model": "rules-v1",
  "ai_degraded": false,
  "duration_ms": 18,
  "created_at": "2026-11-15T23:06:12Z"
}
```

**Vereditos**: `excellent` (≥85), `strong` (≥70), `fair` (≥55), `weak` (<55).

**Erros**: `404 resume_not_found`, `422 validation_error`, `422 job_description_too_long`,
`401 not_authenticated`.

---

### `GET /analyses`

Query: `page`, `page_size`, `resume_id`, `min_score` (0–100).

```json
{
  "items": [
    {
      "id": "08a2345f-1fc4-4b87-b4b4-4e17882dfebd",
      "resume_id": "67c2d0fc-c599-4e82-928e-6b00f57ba6a8",
      "job_title": "Desenvolvedor Backend Sênior",
      "overall_score": 90.6,
      "verdict": "excellent",
      "ai_provider": "heuristic",
      "ai_degraded": false,
      "created_at": "2026-11-15T23:06:12Z"
    }
  ],
  "total": 1,
  "page": 1,
  "page_size": 20,
  "pages": 1
}
```

---

### `GET /analyses/{analysis_id}`

**200 OK** — relatório completo (payload do `POST`).
**Erros**: `404 analysis_not_found`.

---

### `DELETE /analyses/{analysis_id}`

**204 No Content**. Erros: `404 analysis_not_found`.

---

## Metadados e saúde

### `GET /skills` — autenticado

```json
[
  {"name": "Python", "category": "Programming"},
  {"name": "Docker", "category": "Cloud & DevOps"},
  {"name": "Leadership", "category": "Soft Skills"}
]
```

### `GET /health`

```json
{"status": "ok", "version": "1.0.0", "environment": "development"}
```

### `GET /health/live`

```json
{"status": "alive", "version": "1.0.0", "environment": "development"}
```

### `GET /health/ready`

```json
{"status": "ready", "database": "ok"}
```

Retorna `503 database_unavailable` se o banco não responder.

---

## Fluxo completo (curl)

```bash
BASE=http://127.0.0.1:8000/api/v1

# 1. Registrar
REGISTER=$(curl -s -X POST $BASE/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"ana@example.com","full_name":"Ana Silva","password":"SenhaSegura1"}')

TOKEN=$(echo "$REGISTER" | python -c "import sys,json; print(json.load(sys.stdin)['tokens']['access_token'])")

# 2. Upload
RESUME=$(curl -s -X POST $BASE/resumes \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@curriculo.pdf")
RESUME_ID=$(echo "$RESUME" | python -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 3. Analisar contra uma vaga
curl -s -X POST $BASE/analyses \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"resume_id\":\"$RESUME_ID\",\"job_title\":\"Backend\",\"job_description\":\"Python, FastAPI, Docker\"}"

# 4. Dashboard
curl -s $BASE/users/me/stats -H "Authorization: Bearer $TOKEN"
```

---

## Rate limiting

Endpoints `/auth/register`, `/auth/login` e `/auth/refresh` compartilham um limite por IP
(padrão: 30/min). Ao exceder: `429` com `Retry-After` em segundos.

```json
{
  "detail": "Too many requests. Try again in 42 seconds.",
  "code": "rate_limited",
  "details": {"retry_after": 42}
}
```
