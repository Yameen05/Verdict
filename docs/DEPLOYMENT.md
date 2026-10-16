# Production deployment and recovery

Verdict supports **one host and one backend worker**, persistent SQLite, and a
TLS reverse proxy on that host. It is prepared for review, not automatically
approved for public deployment. Read [the audit](SECURITY_AUDIT_2026-10-15.md),
including unresolved OS advisories, before release.

## 1. Production secrets and settings

Use Docker Compose **2.30 or newer**. Store a production environment file outside
the repository, restrict it to its operator (`chmod 600`), and use both Compose
files below. The production overlay excludes the developer `backend/.env`,
forces production mode, disables API docs, enables secure cookies, and binds the
frontend to loopback. Merely passing `--env-file` to the base Compose file does
not replace its service `env_file` entries; `backend/.env` otherwise wins over
root `.env` for duplicate backend settings.

```dotenv
ENVIRONMENT=production
CORS_ORIGINS=https://verdict.example.com
ALLOWED_HOSTS=verdict.example.com
APP_PUBLIC_URL=https://verdict.example.com
DOCS_ENABLED=false
SESSION_COOKIE_SECURE=true
APP_PORT=8080
AUTH_BOOTSTRAP_TOKEN=YOUR_UNIQUE_RANDOM_VALUE
```

Replace the example domain with your actual domain. Generate the bootstrap token
with `openssl rand -base64 48`; put it in the environment file/secret manager,
never a command-line argument, frontend variable, report, or Git commit. The app
rejects insecure production settings. Bootstrap is allowed only while no owner exists, and the database's unique
owner key prevents concurrent owner creation. Pre-owner member rows from an
older release can be preserved while the token holder completes owner setup. Password or Google signup cannot precede owner setup.

Confirm data-provider rights before enabling public access. NewsAPI's free
Developer plan excludes staging/production (including internal production);
leave `NEWS_API_KEY` blank or obtain an appropriate plan. Yahoo and other market
feeds also need a permitted production use/redistribution arrangement. See the
providers' current terms; this audit did not inspect account subscriptions.

Configure only the providers you need. LLM and embedding keys stay on the
backend. Production custom provider URLs must use HTTPS, without embedded
credentials or query parameters. Use an actual SEC contact User-Agent. Set
billing/usage limits at providers: app operation counts are not dollar ceilings.
Market-data fetches, readiness and background alerts/grading consume separate
provider quotas outside the LLM/embedding operation counter.

## 2. TLS and proxy boundaries

Terminate TLS at a maintained edge proxy and forward to `127.0.0.1:8080`.
Do not expose backend port 8000 or publish the frontend directly on a public
interface. Redirect public HTTP to HTTPS. Restrict firewall/security-group
access, patch the host and Docker engine, and keep Docker administration private.

For a host nginx TLS server, the relevant upstream block is:

```nginx
location / {
    proxy_pass http://127.0.0.1:8080;
    proxy_set_header Host $http_host;
    proxy_set_header X-Forwarded-Proto https;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_buffering off;
    proxy_read_timeout 660s;
}
```

Configure the certificate, TLS protocols, public HTTP redirect, and server name
in the edge's own configuration. **Overwrite** forwarded protocol at the edge;
never copy a client-supplied value. Append the actual client address to the
forwarded chain. The bundled frontend preserves an edge `https` value and adds
its peer. Gunicorn/Uvicorn forwarded-address rewriting is disabled so the app
resolves IPs itself, right to left. Malformed hops fail closed.

`TRUSTED_PROXY_IPS` defaults to loopback and private networks for Compose.
Narrow it to actual edge/Compose proxy addresses or dedicated subnets when
known. Trusting all private addresses also trusts other machines/containers on
those networks. Do not share this backend network with untrusted workloads.
Production rejects default-route CIDRs and invalid entries. A changed network
must be tested for real IP attribution and shared-NAT throttling behavior.

The frontend `/healthz` probe is redirect-free and uses IPv4. Browsing
`127.0.0.1:8080` still redirects to `localhost:8080` for local Google OAuth.
The backend permits loopback requests to the fixed `/health` liveness route
regardless of public host configuration; every other route retains host checks.
Liveness means the process is up. Authenticated `/api/health/ready` also checks
DB access and configured providers, is throttled, and can report degraded state.

## 3. Build, start, and bootstrap

Use the same exported file and Compose arguments for every command:

```bash
export VERDICT_ENV_FILE=/absolute/secure/path/verdict.env
docker compose --env-file "$VERDICT_ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml config --quiet
docker compose --env-file "$VERDICT_ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml build --pull
docker compose --env-file "$VERDICT_ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml up -d --wait
docker compose --env-file "$VERDICT_ENV_FILE" -f docker-compose.yml -f docker-compose.production.yml ps
```

Do not run plain `docker compose config` in shared logs: it expands secrets.
Verify the public certificate, HTTP redirect and `/api/health`, then use the
HTTPS UI for owner setup. New/reset passwords require 15–128 characters, an
uppercase letter and a digit. Existing account passwords remain usable. Session
cookies use `__Host-`, `Secure`, `HttpOnly`, `SameSite=Strict`, and `Path=/`.
They expire by server TTL/idle checks; browser-session cookies do not imply
infinite server lifetime. Password reset revokes existing app sessions.

## 4. Google sign-in and email recovery

Create a Google OAuth Web application client, authorize the exact public HTTPS
origin, and set `GOOGLE_CLIENT_ID`. The popup flow needs no client secret or
redirect URI. Preserve the bundled CSP and `same-origin-allow-popups` policy.
Test real Google sign-in on the real origin before release. Google cannot create
the first owner. Linking a previously unlinked password account requires its
current authenticated session and CSRF token; a signed-out email match alone is
rejected. Already linked Google accounts keep working.

Recovery remains disabled while SMTP is absent. To enable it, supply the actual
provider's host, port, authenticated username/password (when required), and a
verified sender in `SMTP_FROM`. Set the real `APP_PUBLIC_URL`, matching a CORS
origin. For submission port 587 use `SMTP_STARTTLS=true, SMTP_SSL=false`; for
implicit TLS on 465 use `SMTP_SSL=true, SMTP_STARTTLS=false`. Both modes verify
certificates. Production refuses plaintext recovery delivery, including an
unauthenticated plaintext relay. Development-only local relays remain supported.

Reset requests return the same response regardless of account existence.
Delivery occurs after the response, is best effort rather than a durable mail
queue, and failures are logged/audited without a usable outstanding token.
Restart/crash during delivery can lose mail; a user may request another link.
New links put their token in a URL fragment and the UI removes it immediately.
Legacy query links are still accepted. Neither nginx nor Gunicorn access logs
record query strings. Restrict and rotate logs and avoid recording full URLs at
the external edge, email provider or monitoring agent.

SMTP configuration does not prove deliverability. Verify sender/domain ownership,
SPF/DKIM/DMARC, provider policy and bounce handling, then test one actual recovery
email and one alert before advertising the feature. No real email was sent by
the audit. Public password signup does not verify email ownership; avoid treating
its email field as a verified identity. Invite-only mode is available through
`PUBLIC_SIGNUP_ENABLED=false`.

## 5. Resource and spending controls

`DAILY_RUNS_PER_USER` and `DAILY_RUNS_GLOBAL` now reserve persistent, atomic
operation slots **before** research, chat, timing/day-trade cache misses and
filing ingest/query. One operation can make several LLM/embedding calls. Failed,
cancelled and unsaved operations still count; billing may already have occurred.
Cached research and cached timing/day-trade results do not spend another slot.
UTC-day counters survive restarts. Existing research history seeds first-use
counters during upgrades. These limits are intentionally communal and can be
exhausted by a member; use invitation mode/edge abuse controls when appropriate.

Additional fixed-window controls are 10 password-login attempts per normalized
email per 15 minutes, 3 reset requests per email per hour, 100 new registrations
per UTC day, and 240 authenticated reads/120 writes per account per minute.
Per-IP endpoint limits apply separately. Account throttling can temporarily deny
legitimate users under targeted attack; no permanent account lock is introduced.

The ASGI cap defaults to 1 MiB per body, 8 concurrent expensive requests and a
whole-request deadline (`REQUEST_TIMEOUT_SECONDS`, including ingestion/SSE).
Excess work gets 503 with Retry-After; oversized bodies get 413. SQLite write
caps serialize watchlists, alerts, levels and saved-strategy admissions. Workspace
caps are 24 watchlist symbols, 50 alerts, 20 levels per ticker/200 total levels,
100 tracked positions, 100 verdict watches and 30 strategies. Historical user
records are not trimmed to enforce new caps.

SEC downloads stop above 25 MiB decompressed; filing indexing rejects text above
2 million characters or 2,500 chunks. An oversized filing can leave the analysis
without that evidence; it must not be represented as a complete filing review.
Async cancellation cannot forcibly terminate a synchronous worker thread already
inside a provider call; its own network timeout and container CPU/memory limits
bound that remaining work. Host/edge protections remain necessary for volumetric
attacks.

The base Compose file limits backend memory/CPU to 2 GiB/2 CPUs and frontend to
256 MiB/1 CPU, plus PID limits, read-only filesystems, non-root users, no added
capabilities and no-new-privileges. Tune measured capacity via the example env
fields. Docker logs rotate at 10 MiB × 3 per service. Persistent DB/history/audit
storage still grows: monitor disk space, failed logins, 429/5xx rates, provider
budgets and backup age. Expired sessions, reset/Google challenges and price
previews are cleaned hourly; users, trades, research and audit history remain.

## 6. Backup and recovery

Never copy only a live SQLite `.db` while its WAL is active. Use SQLite's online
backup API; the supplied CLI snapshots both app and local-vector databases,
checks integrity/foreign keys, writes SHA-256 manifests and uses private file
permissions. Pinecone is external and needs its own recovery/re-ingest plan.

Example inside the backend (use a fresh output name for every recovery point):

```bash
python -m app.scripts.backup_sqlite --output-dir /tmp/verdict-backup-20261015
python -m app.scripts.backup_sqlite --verify /tmp/verdict-backup-20261015
```

Run these via `docker compose ... exec -T backend`, then copy the directory to a
private host backup directory with `docker cp`. `/tmp` is disposable and limited:
a large production DB needs a dedicated private backup mount with enough space.
A path under the writable data volume also works as temporary staging, but is
not an independent backup. Encrypt and copy off-host; set retention, ownership,
backup scheduling and alerts. Backups contain password hashes and live session
material. A manifest detects accidental changes; it does not authenticate a
backup against an attacker who can rewrite the manifest. Keep backups and their
trusted digests under separate access controls.

Restoration procedure:

1. Verify the manifest/integrity on an isolated recovery copy.
2. Stop backend/background workers. Preserve the current volume as a separate
   rollback point; never run `down --volumes` on production.
3. Restore `verdict.db` and, when used, `vectors.db` to the configured data paths;
   remove stale WAL/SHM files only for the stopped, replaced database copies.
4. Restore owner UID 10001 permissions; start the same reviewed image/config.
5. Check migrations, liveness/readiness, owner login, a private workspace item,
   saved research/track-record timestamps, and an isolated recovery flow.
6. Invalidate restored sessions/reset tokens if recovering from compromise or a
   stale backup. Do not reset user passwords or delete accounts indiscriminately.

The audit verified synthetic WAL snapshots and an isolated production restart;
it did not restore or inspect the user's live account database. Define acceptable
RPO/RTO and exercise a complete host-loss restoration before public release.
Schema migrations run at startup; back up before upgrading and do not roll back
an image across incompatible schema changes without a tested data rollback.

## 7. Release verification

```bash
cd backend
../.venv/bin/ruff check app/
../.venv/bin/pytest -q
../.venv/bin/pip-audit -r requirements-dev.txt
../.venv/bin/bandit -q -r app -x app/tests
cd ../frontend
npm ci
npm test
npm run build
npm audit
cd ..
gitleaks git --redact --config .gitleaks.toml
docker build --pull -t verdict-security-backend:audit backend
docker build --pull -t verdict-security-frontend:audit frontend
python3 scripts/verify_release.py
```

The smoke script generates a separate Compose project, synthetic credentials,
a one-day test TLS certificate trusted explicitly by its client, and a new
volume. It checks production startup, both probes, actual TLS, security headers,
authentication, CSRF/origins/hosts, user isolation, body caps, cached SSE, backup
verification and persistence after restart, then removes **only its own** test
containers/volume. It does not read developer environment files, send email,
call paid providers or validate a real public certificate/domain.

CI audits dependencies/secrets, lints/tests/builds, scans both runtime images,
retains complete image reports, rejects fixable high/critical findings, and runs
this smoke test. Review unresolved findings separately: CI is not authorization
to accept unfixed vulnerabilities or deploy publicly. Rebuild regularly to get
OS security updates; digest-pinned bases and Python constraints require reviewed
updates. Keep one backend worker. Scaling requires coordinated background jobs,
shared limits and a database concurrency/recovery design; enabling Redis alone
is not a complete scaling solution.

## 8. Signup agreement and public-launch disclosures

New-account creation now requires explicit agreement to current Terms of Service,
understanding of the Risk & Data Disclosure and receipt of the Privacy Notice.
The compact signup agreement applies to owner bootstrap, public/invite email signup
and first-time Google signup. A Google login for an unknown identity with no
agreement returns HTTP 428 without creating an account; its single-use nonce is
still consumed. Review the documents and restart Google with a fresh challenge.
Existing password/linked-Google login and authenticated linking remain usable
without fabricated acceptance records.

`legal_acceptances` is an additive table keyed by user ID. Versions, source
fingerprint and server UTC acceptance time are committed with account creation;
`account_legal_agreement` also records request-associated audit evidence. Existing
users receive no backfilled rows. This evidence records an affirmative request,
not proof that a person read every word or that any clause is legally enforceable.

When legal copy changes, assign new affected document versions, regenerate the
SHA-256 of `frontend/src/lib/legal.ts`, and update **both**
`backend/app/legal_manifest.json` and `frontend/src/lib/legalManifest.json` in the
same release. The manifest-contract test rejects source/fingerprint drift. Deploy
the matching frontend and backend together: stale frontend versions cannot create
accounts. Retain the released source/artifact with each version in reviewed Git
history. The software does not silently record later agreement for older users;
any future reacceptance requirement needs a separate reviewed design.

Before public launch, complete these deployment-specific inputs:

- Actual operator/legal identity, jurisdiction, intended users, contact details
  and free/subscription/advertising/affiliate model, including any conflicts.
- Qualified review of research/recommendation behavior, applicable registration
  or exemption requirements, agreement wording and non-waivable consumer rights.
  Disclaimers are not immunity or a legal-compliance determination.
- A real privacy-rights/deletion request channel and implemented procedure,
  retention/backups schedule, provider/hosting inventory and processing settings.
  This release has no self-service account deletion or implemented request channel.
- Commercial/public-display/redistribution permission for configured data and AI
  services. NewsAPI's Developer plan excludes staging/production; yfinance warns
  about personal use. A working API key does not resolve these licenses.
- The operational gates elsewhere in this document: public TLS/domain, provider
  setup, SMTP/recovery, monitoring, off-host backup/restoration and unresolved
  runtime-image advisories.

See [the official-source comparison](TERMS_COMPARISON_2026-10-15.md). Keep copy
aligned with actual behavior: chat questions/history can send personal details to
AI providers, scores are model assessments rather than profit probabilities, and
historical/practice outcomes do not forecast actual account returns.

Optional actual-browser check on this Mac (requires installed local Chrome and
`frontend/node_modules/puppeteer-core`; it uses a new temporary browser profile):

```bash
python3 scripts/verify_release.py --browser-check
```

It creates a synthetic email account in the disposable TLS instance, verifies the
unchecked/disabled agreement control, readable linked modal documents, preserved
form values, Back/reset behavior and desktop/mobile width. It captures
`security-audit/signup-agreement.png` and `security-audit/signup-mobile.png`.
The Google UI handoff uses local GIS/API test doubles; backend JWT tests cover
first-time agreement and challenge replay. Neither verifies live Google login or
uses the user's Chrome profile/credentials.
