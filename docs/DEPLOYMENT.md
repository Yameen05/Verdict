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

Generate the one-time owner bootstrap token:

```bash
openssl rand -base64 48
```

Store the value in `AUTH_BOOTSTRAP_TOKEN` and keep it in a secret manager.

Configure the provider keys needed for the features you will use. Never put
provider keys or authentication secrets in frontend build variables.

For Google sign-in, create a Google OAuth **Web application** client and add
your HTTPS site origin to its Authorized JavaScript origins. Set
`GOOGLE_CLIENT_ID` in the backend environment and restart the backend. No
client secret or redirect URI is needed for the popup flow. The bundled nginx
policy permits Google's sign-in script, styles, connections, and frames, and
uses `same-origin-allow-popups` so popup communication works. Preserve these
headers if you add another reverse proxy. Test a real Google login from the
authorized HTTPS origin before release. Signup and invite rules still apply;
Google sign-in cannot create the first owner.

## 2. Put TLS in Front

Terminate HTTPS with a maintained reverse proxy or managed load balancer and
forward traffic to `http://127.0.0.1:8080`. Preserve the original `Host` and
`X-Forwarded-Proto` headers. Do not publish backend port 8000.

Your proxy must **append** the real peer to `X-Forwarded-For` rather than
replacing it — nginx's `$proxy_add_x_forwarded_for` does this, and the bundled
config already uses it. The app resolves the client address by walking that
header right to left, skipping hops listed in `TRUSTED_PROXY_IPS`, so a value a
client forged for itself is always overridden by the address the proxy appended.
Rate limits and audit records key off the result.

`TRUSTED_PROXY_IPS` defaults to loopback plus the private ranges, which covers
the bundled Compose setup. Set it explicitly if your proxy has a public address.
Never set it to `0.0.0.0/0`: that trusts every peer, which lets any client claim
an arbitrary address and walk past the login and password-reset limits.

Use a DNS name that exactly matches `ALLOWED_HOSTS` and `CORS_ORIGINS`. Verify
the certificate before completing owner setup.

## 3. Create the Owner Account

```bash
docker compose pull
docker compose up --build -d
docker compose ps
curl --fail http://127.0.0.1:8080/api/health
```

Open the HTTPS site, enter the bootstrap token, and create a long unique password.
The database prevents a second owner from being bootstrapped.

## 4. Back Up and Operate

- Back up the `verdict-db` volume and test restoration regularly.
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
