# Verdict

[![Python](https://img.shields.io/badge/python-3.13-blue)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.138-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-0.2-7E57C2)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev/)
[![Tests](https://img.shields.io/badge/tests-pytest%20%2B%20tsc-brightgreen)](backend/app/tests)
[![License](https://img.shields.io/badge/license-MIT-lightgrey)](LICENSE)

Verdict is a full-stack, multi-agent equity research app. Enter a ticker and
it builds a structured research report from SEC filing retrieval, recent news
sentiment, and live financial metrics.

> This project is for software demonstration and research workflow exploration.
> It is not financial advice.

![Verdict dashboard](docs/assets/verdict-dashboard.jpg)

## What It Does

- Ingests the latest SEC `10-K` or `10-Q` filing for a ticker.
- Chunks and embeds filing text into Pinecone for per-ticker retrieval.
- Runs a LangGraph research pipeline with specialist agents for:
  - SEC filing RAG
  - recent news sentiment
  - financial metrics from yfinance
- Streams agent progress to the browser over Server-Sent Events.
- Synthesizes a final `Buy`, `Hold`, `Sell`, or `Pending` report with concrete
  justification.
- Persists completed research runs to SQLite for history and comparison.
- Tracks LLM and embedding token usage with estimated cost per research request.

## Architecture

```text
React + TypeScript SPA
  live progress, filing ingest, ad-hoc RAG query, report history
        |
        | REST + Server-Sent Events
        v
FastAPI backend
  owner auth, mandatory TOTP 2FA, CSRF protection, rate limiting, JSON audit logs
        |
        v
LangGraph StateGraph
  START
    |--------------------|----------------------|
    v                    v                      v
  SEC agent           News agent             Metrics agent
  Pinecone RAG        NewsAPI + VADER        yfinance TTM metrics
    |--------------------|----------------------|
                         v
                   Synthesizer
                   LLM JSON report
                         |
                         v
                   SQLite research_runs
```

The backend is designed to degrade cleanly. Missing NewsAPI credentials skip the
news agent; missing filing vectors skip the SEC agent; upstream failures return
typed `error` payloads instead of crashing the whole graph.

## Tech Stack

| Layer | Tools |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS |
| API | FastAPI, Uvicorn, Gunicorn, SlowAPI, SSE Starlette |
| Agent orchestration | LangGraph `StateGraph` |
| LLM and embeddings | OpenAI-compatible chat completions, OpenAI embeddings |
| Retrieval | Pinecone serverless index, namespace per ticker |
| Market/news data | SEC EDGAR, NewsAPI, VADER, yfinance |
| Persistence | SQLAlchemy async ORM, SQLite by default |
| Ops | Docker, Docker Compose, nginx SPA proxy, structured JSON logs |
| Tests | pytest, pytest-asyncio, pytest-httpx, ruff, TypeScript build |

## Repository Layout

```text
verdict/
├── backend/
│   ├── app/
│   │   ├── agents/              # LangGraph state and agent nodes
│   │   ├── observability/       # JSON logs and token/cost tracking
│   │   ├── persistence/         # async SQLAlchemy history store
│   │   ├── routers/             # health, filings, research endpoints
│   │   ├── schemas/             # Pydantic API models
│   │   ├── services/            # SEC, Pinecone, LLM, embeddings, NewsAPI, yfinance
│   │   └── tests/               # mocked backend test suite
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/client.ts        # typed REST and SSE client
│   │   ├── components/          # input, progress, report, history panels
│   │   └── App.tsx
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── nginx.conf
├── docs/assets/
│   └── verdict-dashboard.jpg
├── docker-compose.yml
├── docker-compose.dev.yml
├── .env.example
└── Makefile
```

## Quickstart

### 1. Configure Environment

```bash
cp .env.example .env
```

Fill in at least:

```bash
LLM_API_KEY=...
SEC_USER_AGENT="Verdict Research your.email@example.com"
AUTH_BOOTSTRAP_TOKEN="$(openssl rand -base64 48)"
AUTH_ENCRYPTION_KEY="$(openssl rand -base64 32 | tr '+/' '-_')"
```

Optional:

```bash
OPENAI_API_KEY=...
PINECONE_API_KEY=...
NEWS_API_KEY=...
```

The default `.env.example` is configured for Google Gemini through its
OpenAI-compatible endpoint. To use OpenAI for chat instead, leave
`LLM_BASE_URL` blank, set `LLM_MODEL=gpt-4o-mini`, and put the key in
`OPENAI_API_KEY`.

SEC filing ingestion and filing search use OpenAI embeddings plus Pinecone, so
set `OPENAI_API_KEY` and `PINECONE_API_KEY` when you want the filing RAG path.

On first launch, the browser asks for `AUTH_BOOTSTRAP_TOKEN`, creates the sole
owner account, and requires TOTP enrollment. Save the one-time recovery codes in
a password manager. The bootstrap route closes permanently once the owner exists.

### 2. Run With Docker

```bash
docker compose up --build
```

- Frontend: http://localhost:8080
- Backend: internal-only in the production Compose stack
- API docs: available on http://localhost:8000/docs with the development override

### 3. Run With Hot Reload

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Frontend with Vite HMR: http://localhost:5173
- Backend API: http://localhost:8000

## API Overview

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Liveness probe |
| `POST` | `/auth/bootstrap` | One-time owner creation |
| `POST` | `/auth/login` | Password sign-in |
| `POST` | `/auth/2fa/verify` | TOTP or recovery-code verification |
| `GET` | `/health/ready` | Authenticated dependency readiness |
| `POST` | `/filings/ingest` | Fetch SEC filing, chunk, embed, and upsert to Pinecone |
| `POST` | `/filings/query` | Query previously ingested filing chunks |
| `POST` | `/research/{ticker}` | Run the full research graph and persist the result |
| `GET` | `/research/{ticker}/stream` | Stream agent progress and final result via SSE |
| `GET` | `/research/history/{ticker}` | Return recent persisted research runs |

Unauthenticated liveness check:

```bash
curl --fail http://localhost:8080/api/health
```

Use the browser client for protected routes; it manages the HttpOnly session,
2FA challenge, and per-session CSRF token.

## Configuration

| Variable | Required | Description |
| --- | --- | --- |
| `LLM_API_KEY` | For custom LLM | Chat model key for `LLM_BASE_URL` providers |
| `LLM_BASE_URL` | No | OpenAI-compatible chat endpoint; blank uses OpenAI |
| `OPENAI_API_KEY` | For SEC RAG / OpenAI chat | OpenAI embeddings; also used for chat when `LLM_BASE_URL` is blank |
| `PINECONE_API_KEY` | For SEC RAG | Filing vector store |
| `PINECONE_INDEX_NAME` | No | Defaults to `verdict-filings` |
| `PINECONE_CLOUD` | No | Defaults to `aws` |
| `PINECONE_REGION` | No | Defaults to `us-east-1` |
| `SEC_USER_AGENT` | Yes | SEC EDGAR requires an app/contact user agent |
| `NEWS_API_KEY` | No | Enables the news agent; missing key skips news |
| `NEWS_LOOKBACK_DAYS` | No | Defaults to `30` |
| `NEWS_MAX_ARTICLES` | No | Defaults to `30` |
| `EMBEDDING_MODEL` | No | Defaults to `text-embedding-3-small` |
| `LLM_MODEL` | No | Defaults to `gemini-2.0-flash` in `.env.example`; app default is `gpt-4o-mini` |
| `AUTH_BOOTSTRAP_TOKEN` | Yes | One-time owner-creation secret; generate at least 32 random characters |
| `AUTH_ENCRYPTION_KEY` | Yes | Fernet key used to encrypt the TOTP seed at rest |
| `SESSION_COOKIE_SECURE` | Production | Must be `true` behind HTTPS |
| `REQUIRE_2FA` | No | Defaults to `true` |
| `RATE_LIMIT_AUTH` | No | Defaults to `5/minute` |
| `RATE_LIMIT_RESEARCH` | No | Defaults to `30/minute` |
| `RATE_LIMIT_FILINGS` | No | Defaults to `60/minute` |
| `DATABASE_URL` | No | Defaults to local SQLite at `./data/verdict.db` |
| `CORS_ORIGINS` | No | Comma-separated allowed origins |

## Local Development

Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
uvicorn app.main:app --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Useful Make targets:

```bash
make backend-test
make frontend-install
make pinecone-init
make fetch-sample TICKER=AAPL
```

## Tests And Checks

```bash
cd backend
python -m ruff check app
python -m pytest -q

cd ../frontend
npm run lint
npm run build
```

Current local verification:

- Backend ruff: passing
- Backend pytest: `68 passed`
- Frontend TypeScript/build: passing

## Security And Publish Notes

The repository is intended to be safe to publish with only placeholder
configuration committed.

- Real credentials belong in `.env`, which is ignored by git.
- `.env.example` contains empty placeholders only.
- Docker build contexts ignore `.env`, local virtualenvs, logs, caches, and build
  outputs.
- Runtime SQLite files under `backend/data/` or `data/` are ignored.
- Local tool state under `.swarm/` is ignored and should not be committed.
- TypeScript build-info files are ignored.
- The backend logs request IDs and operational metadata, but should not log raw
  API keys, passwords, session tokens, TOTP values, or recovery codes.
- Passwords use Argon2id. Session tokens are random, stored only as SHA-256
  digests, and delivered in HttpOnly/Secure/SameSite cookies.
- TOTP seeds are encrypted at rest; recovery codes are one-time and keyed-hashed.
- Every non-health API route requires an authenticated, 2FA-verified session.
- State-changing requests require a per-session CSRF token and an allowed Origin.
- Research history is scoped to the authenticated owner.

Before publishing, run:

```bash
find . -name ".env" -o -name "*.pem" -o -name "*.key" -o -name "*.db" -o -name "*.sqlite"
rg -n --hidden --glob '!.git/**' --glob '!frontend/node_modules/**' \
  --glob '!backend/.venv/**' --glob '!frontend/dist/**' \
  'sk-[A-Za-z0-9_-]{20,}|pcsk_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
```

## Production Considerations

- Use a real secret manager for API keys.
- Set `ENVIRONMENT=production`, `DOCS_ENABLED=false`,
  `SESSION_COOKIE_SECURE=true`, and explicit `ALLOWED_HOSTS` /
  `CORS_ORIGINS`.
- Terminate TLS in a maintained reverse proxy or managed load balancer. The
  Compose port binds to loopback by default so the backend and raw HTTP service
  are not directly internet-exposed.
- Keep `CORS_ORIGINS` narrow.
- Move from SQLite to Postgres for multi-instance deployments.
- Add budget/rate controls for upstream LLM, OpenAI embeddings, Pinecone, NewsAPI, and Yahoo
  Finance calls.
- Do not present model output as investment advice without human review and
  appropriate compliance controls.

## License

MIT. See [LICENSE](LICENSE).
