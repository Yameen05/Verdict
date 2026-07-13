<p align="center">
  <img src="frontend/public/verdict.svg" alt="Verdict logo" width="88" />
</p>

<h1 align="center">Verdict</h1>

<p align="center">
  <strong>Multi-agent market research that argues both sides before it makes the call.</strong>
</p>

<p align="center">
  <a href="#product-tour">Product tour</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quickstart">Quickstart</a> ·
  <a href="docs/DEPLOYMENT.md">Deployment</a> ·
  <a href="SECURITY.md">Security</a>
</p>

[![Python](https://img.shields.io/badge/Python-3.13-blue)](https://www.python.org/)
[![Node](https://img.shields.io/badge/Node-22-43853D)](https://nodejs.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.138-009688)](https://fastapi.tiangolo.com/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.2-7E57C2)](https://langchain-ai.github.io/langgraph/)
[![React](https://img.shields.io/badge/React-18-61DAFB)](https://react.dev/)
[![License](https://img.shields.io/badge/License-MIT-lightgrey)](LICENSE)

Verdict is a full-stack, multi-agent stock and crypto research workspace. Pick a
ticker, choose how long you would hold it, inspect the live chart, and get a
plain-English Buy / Hold / Sell report that explains what could happen to a
specific dollar amount over 1 week, 2 weeks, 1 month, 3 months, and 1 year.
A separate day-trading desk runs five intraday agents plus a risk manager for
buy / sell / stand-aside calls with an entry, stop, and target. The UI ships
in an editorial "ink & copper" theme — warm ink surfaces, copper accents, a
serif display face for the big moments, and a matching warm-paper light mode.

> Verdict is a software demo and research workflow exploration tool. It is not
> financial advice.

![Verdict research dashboard](docs/assets/verdict-live-dashboard.png)

| Research | Trading | Accountability |
| --- | --- | --- |
| SEC filings, news, fundamentals, insiders, and optional market signals | Live charts, timing checks, alerts, position planning, and a five-agent intraday desk | Bull/bear debate, citable evidence, dissent, history, backtests, and confidence calibration |

## Product Tour

The app is organized into five pages: **Research**, **Day trading**,
**Analyst**, **History**, and **Scoreboard**.

### Research Workspace

Verdict starts with a protected research dashboard: stock/crypto picker,
watchlist, live backend readiness, SEC filing tools, holding-period controls,
and a one-click `Analyze` flow. The app is built around simple questions like
"If I invest $200 right now, what could I get in 1 week, 2 weeks, or later?"

### Live Chart

The chart is interactive and built for TradingView-style workflows: candles,
area/line views, volume, SMA overlays, Bollinger bands, RSI, MACD, log scale,
range/interval controls, comparison tickers, live polling, price alerts,
verdict markers, event markers, and decision lines.

![Verdict live chart](docs/assets/verdict-live-chart.png)

### Planning Panels

The side panels translate the chart and verdict into practical numbers:
position tracking for "I bought last week, should I hold or sell?", a return
range table for "What might $200 turn into?", smart alerts, timing checks, and
tooltips that explain phrases like "wait for a pullback." Watchlist, positions,
alerts, chart levels, and verdict watches are stored on your account, so they
follow you across browsers and devices.

![Verdict planning panels](docs/assets/verdict-live-planning-panels.png)

### Day-Trading Desk

A dedicated page for intraday decisions on any searchable symbol. Five
deterministic desk agents read the tape — trend (9/20 EMA stack, prior-day
territory), momentum (5-minute RSI and MACD), volume/VWAP, levels
(opening-range breakouts, high/low of day), and catalyst (gaps, news flow) —
and a risk manager demands multi-agent confluence and at least 1.3R before it
signs off on **Buy / Sell / Stand aside** with a structure-based entry, stop,
target, and risk:reward. When an LLM is configured, a "head trader" prompt
that encodes day-trading discipline (trade the VWAP side, skip the lunch
chop, never chase extended moves) synthesizes the final call, with the
deterministic desk as fallback and audit trail. The page adds a rules-only
scanner that ranks liquid names by setup strength, a position-size calculator
that works from the stop distance, 60-second auto-refresh, and a US session
clock (opening drive, lunch, power hour; crypto is 24/7). Most of the day the
honest answer is "stand aside" — and the desk says so.

![Verdict day-trade desk](docs/assets/verdict-live-daytrade.png)

### Alerts That Work While You Sleep

Price alerts and "tell me when the verdict changes" watches are evaluated by a
background worker inside the API process — they trigger even when no tab is
open, and can send email when SMTP is configured. The chart still fires
instant browser notifications for crossings you are watching live.

### The Trial

Each run gathers evidence in parallel: SEC filing RAG, news sentiment, Yahoo
Finance metrics, insider Form 4 activity, and optional market-signal providers
such as Alpha Vantage, Finnhub, Polygon, Tiingo, FRED, Reddit, and StockTwits.
A bull advocate and a bear advocate argue opposing cases from the same evidence
ledger. A judge weighs both sides and issues the verdict with confidence,
scorecard dimensions, dissent, falsifiers, and citable evidence ids.

### Ask The Analyst

The analyst lives on its own page as a grounded chatbot. After a report is
generated, the chat is grounded in a
distilled view of that run (verdict, dissent, risks, swing statistics, news,
insider and analyst signals). Money questions like "what happens to my $200?"
are answered by a deterministic calculator with exact dollar ranges — no LLM
call, no cost — while "why?" and "should I sell?" questions go to the model
with the report's reasoning and the strongest opposing argument in hand. The
analyst can also search the indexed filing live when a follow-up needs detail
the report doesn't carry.

### Verdict History

Every past verdict for any ticker lives on its own page: the full run list
with confidence and cost, plus a timeline that plots each call against the
price at the moment it was made — so verdict drift is visible at a glance.

### The Scoreboard

Every verdict stores the price at the moment it was issued — and which model
issued it. The scoreboard tab replays the book: forward return since each
call, hit/miss under a disclosed rule, aggregate hit rate, average return on
Buys, and horizon backtests once a call is old enough to grade. A calibration
panel adds a Brier score and hit-rate-by-confidence buckets, so you can see
whether the app's stated confidence deserves your trust. Verdict grades its
own homework.

![Verdict scoreboard](docs/assets/verdict-live-scoreboard.png)

### Sign-in, Recovery, and Legal

Access starts at a themed sign-in screen with invite registration (or open
signup when enabled), a forgot-password flow, and mandatory acceptance of the
in-app Terms of Use, Privacy Policy, and Risk & Data Disclosure — all three
render inside the app from the sign-in screen and from the footer on every
page.

![Verdict sign-in](docs/assets/verdict-live-signin.png)

Screenshots are captured from the real React UI against a throwaway demo
database (`APP_URL=http://localhost:5173 node frontend/scripts/capture-screenshots.mjs`
rebuilds them).

## What It Does

- Small-circle multi-user: the bootstrap owner mints one-time invite codes
  (7-day expiry, digest-only storage); friends register with a code — no email
  service required. Password auth, optional TOTP 2FA, HttpOnly sessions, CSRF
  protection, origin checks, and rate limits for every account. Flip
  `PUBLIC_SIGNUP_ENABLED=true` to open self-serve registration (daily run
  quotas still cap spend).
- Account recovery: a forgot-password flow emails a single-use, digest-stored
  reset link when SMTP is configured; a successful reset revokes every session
  for the account. The sign-in screen only offers the link when the server can
  actually send it.
- Legal pages built in: Terms of Use, Privacy Policy, and a Risk & Data
  Disclosure ("not investment advice"; third-party market data is delayed,
  may be wrong, and is for personal non-commercial use) are rendered in-app
  from the sign-in screen and the footer on every page.
- Free-tier protection built in: research runs are communal — a recent run for
  a ticker is served to everyone from cache (zero LLM cost), and fresh runs
  are capped per user and globally per day (`DAILY_RUNS_PER_USER`,
  `DAILY_RUNS_GLOBAL`, `RESEARCH_CACHE_MINUTES`).
- One-button analysis for stocks and crypto: pick an asset, pick a holding
  period (1 week to 1 year), press Analyze. The filing is fetched and indexed
  automatically on first run; coins skip SEC/insider evidence with a plain
  explanation.
- Live chart workspace: candles, line/area view, volume, indicators, compare
  tickers, live polling, price alerts, verdict markers, event markers, and
  decision lines for support/resistance, entry zones, analyst targets, and
  historical risk bands.
- Plain-English investment planner: enter an amount, purchase date, and
  optional buy price to see current gain/loss, shares, whether the latest read
  says hold/sell/add, and what the same amount could look like over future
  holding windows.
- Account-synced workspace: watchlist, positions, price alerts, chart levels,
  and verdict watches live in the database, scoped per user (`/me` routes).
  Data saved by earlier localStorage-only versions migrates to the account
  automatically on first load.
- Server-side alerting: a background worker checks pending price alerts and
  verdict watches on an interval (`ALERTS_CHECK_SECONDS`), marks crossings,
  and emails the owner of the alert when SMTP is configured (`SMTP_*`).
- Self-calibration: matured verdicts produce a Brier score and
  hit-rate-by-confidence buckets, and every run records the LLM model that
  issued it so track records stay comparable across model swaps.
- Layered market data: Yahoo Finance is primary, with automatic fallback to
  Polygon, Tiingo, and Stooq for daily/weekly history — the chart, return
  ranges, backtests, and chat calculator all survive a Yahoo outage.
- Asset-aware panels: a capabilities endpoint tells the UI which evidence
  exists per asset, so coins show "n/a — coins don't file with the SEC"
  instead of an error-looking "missing" for filings and insider data.
- Horizon-aware verdicts: the debate and judge are framed for the user's
  window, with rolling-window stats from price history, return ranges for
  custom dollar amounts, and an "Explain it simply" mode with zero finance
  jargon.
- Timing agent: combines technicals, recent price behavior, news, optional
  market signals, and the selected horizon into simple advice such as "buy
  now", "wait for a pullback", "hold", or "avoid for this window."
- Day-trade desk: five intraday rule agents (trend, momentum, volume/VWAP,
  levels, catalyst) over VWAP, fast EMAs, opening ranges, prior-day levels,
  ATR, and relative volume; a risk manager that refuses trades below 1.3R or
  without confluence; an optional LLM head trader with deterministic fallback;
  a rules-only market scanner; and a session clock that never issues a live
  entry while the market is closed.
- Fetches the latest SEC `10-K` or `10-Q` for a ticker through SEC EDGAR.
- Chunks filing text, embeds it with the configured embedding provider, and
  stores vectors in a local SQLite vector store by default (or Pinecone when a
  key is set).
- Runs a LangGraph adversarial research graph:
  - five parallel evidence agents — SEC filing RAG, LLM-scored news sentiment,
    yfinance financials, SEC Form 4 insider activity, and optional signal
    providers
  - a deterministic evidence ledger with citable ids
  - bull and bear advocates that argue opposing cases from the same ledger
  - a judge that issues the verdict with confidence, dimension scores,
    dissent, falsifiers, and evidence citations — and may run one targeted
    follow-up retrieval from the filing before deciding
- Streams per-node progress and mid-debate events to the browser over SSE.
- Persists completed runs (with price-at-verdict) in SQLite for history,
  verdict-drift timelines, the self-grading scoreboard, and horizon backtests.
- Shows calibration, disagreement, source quality, API/config status, skipped
  source explanations, and rate-limit/quota-friendly cache status in the UI.
- Tracks prompt, completion, embedding, and estimated USD cost per request.

Verdict degrades intentionally. Missing NewsAPI credentials skip the news
agent. Missing Alpha Vantage, Finnhub, Polygon, Tiingo, FRED, Reddit, or
StockTwits data skips that signal source. Missing filing vectors skip the SEC
RAG path. Upstream failures return typed error payloads instead of taking down
the whole graph — the judge rules on whatever evidence survives.

## Architecture

```text
React + TypeScript + Vite
  five pages: research (picker, live chart, timing, planner, trial),
  day trading (desk, scanner, position sizer), analyst chat,
  verdict history, scoreboard + backtests + calibration
        |
        | REST + Server-Sent Events
        v
FastAPI
  auth, 2FA, CSRF, rate limits, readiness/config health, market data,
  day-trade desk (/daytrade), per-user workspace state (/me),
  background alert worker, JSON logs, persistence
        |
        v
LangGraph StateGraph
  START
    |-----------|-------------|--------------|---------------|
    v           v             v              v               v
  SEC agent   News agent    Metrics agent  Insider agent   Signals agent
  local RAG   NewsAPI +     yfinance       EDGAR Form 4    Alpha Vantage,
  (or         LLM scoring                                  Finnhub, Polygon,
  Pinecone)                                                Tiingo, FRED,
                                                           Reddit, StockTwits
    |-----------|------|------|--------------|---------------|
                       v  join
                 evidence ledger  (citable ids: sec:0, metrics:pe, ...)
                   |         |
                   v         v
              bull advocate  bear advocate
                   |         |
                   v  join   v
                     judge  ── may loop once for a follow-up retrieval
              verdict + confidence + scores + dissent + falsifiers
                       |
                       v
              SQLite research_runs (with price-at-verdict → scoreboard + backtests)
```

## Tech Stack

| Layer | Tools |
| --- | --- |
| Frontend | React 18, TypeScript, Vite, Tailwind CSS (CSS-variable theming), Fraunces/Inter/JetBrains Mono |
| API | FastAPI, Uvicorn, Gunicorn, SlowAPI, SSE Starlette |
| Agents | LangGraph `StateGraph` |
| LLM | Any OpenAI-compatible chat completion endpoint |
| Embeddings | OpenAI embeddings |
| Retrieval | Local SQLite vector store (default) or Pinecone serverless |
| Market and news data | SEC EDGAR (filings + Form 4), NewsAPI, yfinance (primary) with Polygon/Tiingo/Stooq price fallback, Alpha Vantage, Finnhub, FRED, Reddit, StockTwits |
| Sentiment | Batched LLM scoring (finance-aware, per headline) |
| Persistence | SQLAlchemy async ORM, SQLite by default |
| Security | Argon2id, encrypted TOTP seed, one-time recovery codes, CSRF |
| Ops | Docker, Docker Compose, nginx SPA proxy, structured JSON logs |
| Tests | pytest (188 backend), Vitest (33 frontend), pytest-asyncio, pytest-httpx, ruff, TypeScript build |

## Repository Layout

```text
Verdict/
├── backend/
│   ├── app/
│   │   ├── agents/              # LangGraph state and agent nodes
│   │   ├── observability/       # JSON logging and token/cost tracking
│   │   ├── persistence/         # async SQLAlchemy history store
│   │   ├── routers/             # auth, health, filings, research, market, daytrade, /me
│   │   ├── schemas/             # Pydantic request/response models
│   │   ├── services/            # SEC, LLM, embeddings, news, metrics, market signals, day-trade desk
│   │   └── tests/               # mocked backend test suite
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── api/                 # typed REST/SSE client split: http, auth, types, user state
│   │   ├── components/          # auth, picker, chart (chart/ hooks + controls), daytrade/, report, planner, chat
│   │   ├── lib/                 # pure logic: position math, disagreements, migration
│   │   └── App.tsx
│   ├── scripts/                 # README screenshot capture (puppeteer-core)
│   ├── Dockerfile
│   ├── Dockerfile.dev
│   └── nginx.conf
├── docs/assets/                 # README screenshots
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

Fill in the required security and SEC settings:

```bash
SEC_USER_AGENT="Verdict Research your.email@example.com"
AUTH_BOOTSTRAP_TOKEN="$(openssl rand -base64 48)"
AUTH_ENCRYPTION_KEY="$(python -c 'import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"
```

Then choose your model provider.

For Gemini through its OpenAI-compatible endpoint, keep the default
`LLM_BASE_URL` and set:

```bash
LLM_API_KEY=...
LLM_MODEL=gemini-2.5-flash
```

For OpenAI chat, leave `LLM_BASE_URL` blank and set:

```bash
OPENAI_API_KEY=...
LLM_MODEL=gpt-4o-mini
```

SEC filing search requires an embedding provider. By default it uses OpenAI
embeddings via `OPENAI_API_KEY`; for a Gemini-only setup, set
`EMBEDDING_BASE_URL` and `EMBEDDING_MODEL=gemini-embedding-001` as shown in
[.env.example](.env.example). Vectors live in a local SQLite file by default,
so no separate vector service is required. Set `PINECONE_API_KEY` only if you
want the Pinecone serverless backend instead.

Extra data sources are optional. Blank keys are skipped safely, and free tiers
still have provider rate limits/quotas:

```bash
NEWS_API_KEY=...
ALPHAVANTAGE_API_KEY=...
FINNHUB_API_KEY=...
POLYGON_API_KEY=...
TIINGO_API_KEY=...
FRED_API_KEY=...
STOCKTWITS_ENABLED=true
REDDIT_ENABLED=true
```

### 2. Run With Docker

```bash
docker compose up --build
```

- App: http://localhost:8080
- Backend container: internal to the Compose network
- SQLite data: persisted in the `verdict-db` Docker volume

On first launch, the browser asks for `AUTH_BOOTSTRAP_TOKEN`, creates the owner
account, and requires TOTP enrollment. Save the recovery codes. The bootstrap
route closes permanently once the owner exists.

### 3. Run With Hot Reload

```bash
docker compose -f docker-compose.yml -f docker-compose.dev.yml up --build
```

- Vite frontend: http://localhost:5173
- FastAPI backend: http://localhost:8000
- API docs in development: http://localhost:8000/docs

## Configuration

| Variable | Required | Purpose |
| --- | --- | --- |
| `SEC_USER_AGENT` | Yes | SEC EDGAR contact user agent |
| `AUTH_BOOTSTRAP_TOKEN` | Yes | One-time owner creation secret |
| `AUTH_ENCRYPTION_KEY` | Yes | Fernet key used to encrypt the TOTP seed |
| `LLM_API_KEY` | For custom chat providers | Key for `LLM_BASE_URL` providers such as Gemini or Groq |
| `LLM_BASE_URL` | No | OpenAI-compatible chat endpoint; blank uses OpenAI |
| `OPENAI_API_KEY` | For SEC RAG and OpenAI chat | OpenAI embeddings and optional OpenAI chat |
| `PINECONE_API_KEY` | No | Switches the vector store from local SQLite to Pinecone |
| `VECTOR_DB_PATH` | No | Local vector store file; defaults to `./data/vectors.db` |
| `PINECONE_INDEX_NAME` | No | Defaults to `verdict-filings` |
| `NEWS_API_KEY` | No | Enables the news agent; missing key skips news |
| `ALPHAVANTAGE_API_KEY` | No | Enables Alpha Vantage fundamentals and intraday quote signals |
| `FINNHUB_API_KEY` | No | Enables Finnhub quote, earnings, and analyst rating signals |
| `POLYGON_API_KEY` | No | Enables Polygon snapshot and previous-close signals |
| `TIINGO_API_KEY` | No | Enables Tiingo daily and IEX quote signals |
| `FRED_API_KEY` | No | Enables macro regime context from FRED |
| `STOCKTWITS_ENABLED` | No | Toggles public StockTwits retail sentiment |
| `REDDIT_ENABLED` | No | Toggles public Reddit retail sentiment |
| `SIGNALS_CACHE_SECONDS` | No | Cache TTL for optional market-signal aggregation |
| `EMBEDDING_MODEL` | No | Defaults to `text-embedding-3-small` |
| `DATABASE_URL` | No | Defaults to `sqlite+aiosqlite:///./data/verdict.db` |
| `CORS_ORIGINS` | No | Comma-separated browser origins |
| `SESSION_COOKIE_SECURE` | Production | Set to `true` behind HTTPS |
| `RESEARCH_CACHE_MINUTES` | No | Shared report cache window; cache hits avoid fresh LLM calls |
| `DAILY_RUNS_PER_USER` | No | Per-user fresh research quota |
| `DAILY_RUNS_GLOBAL` | No | Global fresh research quota |
| `ALERTS_CHECK_SECONDS` | No | Background alert/verdict-watch check interval; `0` disables the worker |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USERNAME` / `SMTP_PASSWORD` / `SMTP_FROM` | No | Enables alert and password-reset emails; blank host = alerts trigger in the UI only |
| `PUBLIC_SIGNUP_ENABLED` | No | `true` opens self-serve registration; default is invite-only |
| `PASSWORD_RESET_TOKEN_MINUTES` | No | Reset-link lifetime; defaults to 30 |
| `APP_PUBLIC_URL` | No | Origin used in password-reset links; blank falls back to the first CORS origin |
| `RATE_LIMIT_AUTH` | No | Defaults to `5/minute` |
| `RATE_LIMIT_RESEARCH` | No | Defaults to `30/minute` |
| `RATE_LIMIT_FILINGS` | No | Defaults to `60/minute` |
| `RATE_LIMIT_STORAGE_URI` | No | Redis URI for shared limiter counters; blank = per-process memory |

See [.env.example](.env.example) for the complete set of operational and cost
tracking variables.

## API Overview

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health` | Public liveness probe |
| `GET` | `/health/ready` | Authenticated dependency readiness |
| `GET` | `/health/config` | Authenticated provider/config status without secret values |
| `GET` | `/auth/status` | Bootstrap/login state |
| `POST` | `/auth/bootstrap` | One-time owner creation |
| `POST` | `/auth/login` | Password sign-in |
| `POST` | `/auth/2fa/verify` | TOTP or recovery-code verification |
| `POST` | `/auth/register` | Create an account with an invite code (or without one when `PUBLIC_SIGNUP_ENABLED=true`) |
| `POST/GET/DELETE` | `/auth/invites` | Owner mints, lists, and revokes one-time invite codes |
| `POST` | `/auth/password-reset/request` | Email a single-use reset link (enumeration-safe; requires SMTP) |
| `POST` | `/auth/password-reset/confirm` | Set a new password and revoke all sessions |
| `POST` | `/filings/ingest` | Fetch, chunk, embed, and index the latest filing |
| `POST` | `/filings/query` | Search indexed filing chunks |
| `GET` | `/market/{ticker}/history` | Chart OHLCV bars by range/interval |
| `GET` | `/market/{ticker}/quote` | Latest bar for live chart updates |
| `GET` | `/market/{ticker}/timing` | Technical/timing assessment for a selected horizon |
| `GET` | `/market/{ticker}/ranges` | Return ranges for a custom dollar amount |
| `GET` | `/market/{ticker}/capabilities` | Which evidence exists for this asset (equity vs crypto) |
| `GET` | `/market/backtest` | Horizon-aware hit-rate and return backtests |
| `GET` | `/daytrade/{ticker}/signal` | Multi-agent intraday buy/sell/stand-aside signal with entry, stop, target |
| `GET` | `/daytrade/scan` | Rules-only sweep of liquid day-trading names, strongest setups first |
| `POST` | `/research/{ticker}` | Run the full adversarial research graph; supports `horizon` and `fresh` query params |
| `GET` | `/research/{ticker}/stream` | Stream node + debate progress and final result over SSE; supports `horizon` and `fresh` query params |
| `POST` | `/research/ask` | Contextual follow-up; can search the filing via tool use |
| `GET` | `/research/history/{ticker}` | Return recent persisted runs |
| `GET` | `/research/scoreboard` | Forward returns and hit rate for past verdicts |
| `GET/POST/DELETE` | `/me/watchlist`, `/me/positions`, `/me/alerts`, `/me/levels`, `/me/verdict-watch` | Per-user workspace state (account-synced) |

Unauthenticated liveness check:

```bash
curl --fail http://localhost:8080/api/health
```

Use the browser client for protected routes. It manages the HttpOnly session,
the 2FA challenge, and the per-session CSRF token.

## Development Commands

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

Checks:

```bash
cd backend
python -m ruff check app
python -m pytest -q

cd ../frontend
npm run lint
npm test
npm run build
```

Current local verification (July 13, 2026):

- Backend lint: `ruff check app` passed.
- Backend tests: `pytest` passed with `188 passed, 9 warnings` (includes the
  day-trade desk suite plus password-reset and public-signup coverage).
- Frontend tests: `vitest` passed with `33 passed` (chart math, position math,
  disagreement logic).
- Frontend production build: `npm run build` passed.

Useful Make targets:

```bash
make dev
make backend-test
make frontend-install
make pinecone-init
make fetch-sample TICKER=AAPL
```

## Security Notes

- Real credentials belong in `.env`, which is ignored by git.
- `.env.example` contains placeholders only.
- Docker build contexts ignore `.env`, local virtualenvs, logs, caches, and
  build outputs.
- Runtime SQLite files under `backend/data/` or `data/` are ignored.
- Passwords use Argon2id.
- Session tokens are random, stored server-side only as SHA-256 digests, and
  delivered in HttpOnly/Secure/SameSite cookies.
- TOTP seeds are encrypted at rest.
- Recovery codes are one-time and keyed-hashed.
- Every non-health API route requires an authenticated, 2FA-verified session.
- Password-reset tokens are single-use, expire in 30 minutes (configurable),
  are stored as SHA-256 digests, and revoke all sessions on success. The
  request endpoint answers identically whether or not the account exists.
- State-changing requests require a per-session CSRF token and an allowed
  `Origin`.
- Research history is scoped to the authenticated owner.

Before publishing, scan for local secrets and databases:

```bash
find . -name ".env" -o -name "*.pem" -o -name "*.key" -o -name "*.db" -o -name "*.sqlite"
rg -n --hidden --glob '!.git/**' --glob '!frontend/node_modules/**' \
  --glob '!backend/.venv/**' --glob '!frontend/dist/**' \
  'sk-[A-Za-z0-9_-]{20,}|pcsk_[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|AKIA[0-9A-Z]{16}|-----BEGIN [A-Z ]*PRIVATE KEY-----'
```

## Production Notes

- Set `ENVIRONMENT=production`, `DOCS_ENABLED=false`,
  `SESSION_COOKIE_SECURE=true`, and explicit `ALLOWED_HOSTS` / `CORS_ORIGINS`.
- Terminate TLS in a maintained reverse proxy or managed load balancer.
- Keep `APP_BIND_ADDRESS=127.0.0.1` when a local reverse proxy owns public TLS.
- Move from SQLite to Postgres for multi-instance deployments: set
  `DATABASE_URL=postgresql+asyncpg://user:pass@host/db` — the asyncpg driver
  ships in requirements.
- Share rate-limit counters before scaling beyond one backend worker: set
  `RATE_LIMIT_STORAGE_URI=redis://host:6379/0` (blank keeps the per-process
  in-memory store, which is correct for a single worker).
- Add provider budgets for LLM, embeddings, Pinecone, NewsAPI, yfinance,
  Alpha Vantage, Finnhub, Polygon, Tiingo, FRED, Reddit, and StockTwits usage.
- Do not present model output as investment advice without human review and
  appropriate compliance controls.

## License

MIT. See [LICENSE](LICENSE).
