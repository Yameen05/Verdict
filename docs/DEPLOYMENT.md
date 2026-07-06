# Production Deployment

Verdict's included Compose stack is a secure single-host baseline. It exposes
only the nginx frontend and keeps FastAPI on the internal Docker network.

## 1. Create Production Configuration

Copy `.env.example` to `.env`, then set at least:

```dotenv
ENVIRONMENT=production
CORS_ORIGINS=https://verdict.example.com
ALLOWED_HOSTS=verdict.example.com
DOCS_ENABLED=false
SESSION_COOKIE_SECURE=true
APP_BIND_ADDRESS=127.0.0.1
APP_PORT=8080
```

Generate independent authentication secrets:

```bash
openssl rand -base64 48
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Put the first value in `AUTH_BOOTSTRAP_TOKEN` and the second in
`AUTH_ENCRYPTION_KEY`. Store both in a secret manager. The encryption key is
required to decrypt enrolled TOTP data; losing it requires account recovery
from a database backup or a controlled re-enrollment.

Configure the provider keys needed for the features you will use. Never put
provider keys or authentication secrets in frontend build variables.

## 2. Put TLS in Front

Terminate HTTPS with a maintained reverse proxy or managed load balancer and
forward traffic to `http://127.0.0.1:8080`. Preserve the original `Host` and
`X-Forwarded-Proto` headers. Do not publish backend port 8000.

Use a DNS name that exactly matches `ALLOWED_HOSTS` and `CORS_ORIGINS`. Verify
the certificate before completing owner setup.

## 3. Start and Enroll the Owner

```bash
docker compose pull
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
```

Open the HTTPS site, enter the bootstrap token, create a long unique password,
and enroll an authenticator. Store the one-time recovery codes separately from
the host. The database prevents a second owner from being bootstrapped.

## 4. Back Up and Operate

- Back up the `verdict-db` volume and test restoration regularly.
- Keep `AUTH_ENCRYPTION_KEY` available to restored instances.
- Run `docker compose logs`, host monitoring, and external uptime checks.
- Review authentication events in the `audit_events` table.
- Apply Dependabot and base-image updates after CI passes.
- Run `pip-audit`, `npm audit`, backend tests, and the frontend build before a
  release.
- Set upstream usage and billing limits with each API provider.

The default SQLite database and in-process rate limiter intentionally run with
one backend worker. Before horizontal scaling, move to Postgres and a shared
rate-limit store, then test session, migration, and recovery behavior under
concurrency.

## 5. Release Check

```bash
docker compose config --quiet
docker compose build
docker compose up -d
curl --fail https://verdict.example.com/api/health
```

Confirm that HTTP redirects to HTTPS, `/api/docs` is unavailable, cookies have
`Secure`, `HttpOnly`, and `SameSite=Strict`, cross-origin writes fail, and the
backend is unreachable directly from the public network.
