"""Disposable production-mode release test, including a real local TLS edge.

Uses only synthetic accounts, generated test credentials, and its own Compose
project/volume. Does not read either developer .env, or contact paid providers.
"""

import argparse
import http.client
import json
import os
import secrets
import socket
import ssl
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def unused_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend-image", default="verdict-security-backend:audit")
    parser.add_argument("--frontend-image", default="verdict-security-frontend:audit")
    args = parser.parse_args()
    project = "verdict-release-" + secrets.token_hex(4)
    with tempfile.TemporaryDirectory(prefix=project) as folder:
        folder = Path(folder)
        http_port, https_port = unused_port(), unused_port()
        token = secrets.token_urlsafe(48)
        env = folder / "test.env"
        env.write_text(f'''ENVIRONMENT=production
SESSION_COOKIE_SECURE=true
AUTH_BOOTSTRAP_TOKEN={token}
ALLOWED_HOSTS=verdict.test
CORS_ORIGINS=https://verdict.test
APP_PUBLIC_URL=https://verdict.test
DOCS_ENABLED=false
PUBLIC_SIGNUP_ENABLED=true
ALERTS_CHECK_SECONDS=0
APP_BIND_ADDRESS=127.0.0.1
APP_PORT={http_port}
REQUEST_TIMEOUT_SECONDS=15
''')
        env.chmod(0o600)
        run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "1",
             "-subj", "/CN=verdict.test", "-addext", "subjectAltName=DNS:verdict.test,IP:127.0.0.1",
             "-keyout", str(folder / "key.pem"), "-out", str(folder / "cert.pem")],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        # Synthetic one-day test key only. The containing host directory is 0700.
        (folder / "key.pem").chmod(0o644)
        edge = folder / "edge.conf"
        edge.write_text('''server {
 listen 8443 ssl;
 ssl_certificate /tls/cert.pem;
 ssl_certificate_key /tls/key.pem;
 location / {
  proxy_pass http://frontend:8080;
  proxy_set_header Host $http_host;
  proxy_set_header X-Forwarded-Proto https;
  proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
  proxy_buffering off;
 }
}
''')
        override = folder / "override.yml"
        override.write_text(f'''services:
  backend:
    image: {args.backend_image}
    env_file: !override
      - path: {env}
  frontend:
    image: {args.frontend_image}
  edge:
    image: {args.frontend_image}
    ports:
      - "127.0.0.1:{https_port}:8443"
    depends_on:
      frontend:
        condition: service_healthy
    volumes:
      - {edge}:/etc/nginx/conf.d/default.conf:ro
      - {folder / 'cert.pem'}:/tls/cert.pem:ro
      - {folder / 'key.pem'}:/tls/key.pem:ro
    healthcheck:
      disable: true
    read_only: true
    tmpfs:
      - /tmp:size=32m,mode=1777
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    pids_limit: 128
    mem_limit: 256m
''')
        os.environ["VERDICT_ENV_FILE"] = str(env)
        os.environ["APP_PORT"] = str(http_port)
        os.environ["APP_BIND_ADDRESS"] = "127.0.0.1"
        compose = ["docker", "compose", "--project-name", project, "--env-file", str(env),
                   "-f", str(ROOT / "docker-compose.yml"),
                   "-f", str(ROOT / "docker-compose.production.yml"), "-f", str(override)]
        context = ssl.create_default_context(cafile=str(folder / "cert.pem"))
        owner_cookie = ""
        csrf = ""

        def request(method, path, data=None, *, owner=False, headers=None, tls=True):
            conn = (http.client.HTTPSConnection("127.0.0.1", https_port, context=context, timeout=20)
                    if tls else http.client.HTTPConnection("127.0.0.1", http_port, timeout=20))
            all_headers = {"Host": "verdict.test"}
            if data is not None:
                all_headers["Content-Type"] = "application/json"
            if owner:
                all_headers.update({"Cookie": owner_cookie, "X-CSRF-Token": csrf})
            all_headers.update(headers or {})
            conn.request(method, path, body=json.dumps(data) if data is not None else None,
                         headers=all_headers)
            response = conn.getresponse()
            body = response.read().decode()
            result = response.status, {key.lower(): value for key, value in response.getheaders()}, body
            conn.close()
            return result

        try:
            run(compose + ["config", "--quiet"], cwd=ROOT)
            run(compose + ["up", "--no-build", "--wait", "--wait-timeout", "120"], cwd=ROOT)
            status, _, _ = request("GET", "/healthz", tls=False, headers={"Host": "127.0.0.1:8080"})
            assert status == 200, "frontend numeric health probe"
            status, headers, _ = request("GET", "/", tls=False, headers={"Host": "127.0.0.1:8080"})
            assert status == 307 and headers["location"].startswith("http://localhost:8080/"), "local OAuth redirect"
            assert request("GET", "/api/health")[0] == 200
            assert request("GET", "/api/docs")[0] == 404
            assert request("GET", "/api/auth/me")[0] == 401
            assert request("GET", "/api/auth/status", headers={"Host": "evil.example"})[0] == 400
            assert request("POST", "/api/auth/register", {"email": "early@example.com", "password": "A-long-password-123"})[0] == 403
            status, headers, raw = request("POST", "/api/auth/bootstrap", {
                "email": "owner@example.com", "password": "A-long-test-password-123",
            }, headers={"X-Bootstrap-Token": token, "Origin": "https://verdict.test"})
            assert status == 201, f"bootstrap status {status}"
            cookie = headers["set-cookie"]
            assert all(value in cookie for value in ("__Host-verdict_session", "Secure", "HttpOnly", "SameSite=strict", "Path=/"))
            owner_cookie = cookie.split(";", 1)[0]
            csrf = json.loads(raw)["csrf_token"]
            assert request("GET", "/api/auth/me", owner=True)[0] == 200
            assert request("POST", "/api/me/watchlist", {"ticker": "TEST"}, owner=True,
                           headers={"X-CSRF-Token": "wrong"})[0] == 403
            assert request("POST", "/api/me/watchlist", {"ticker": "TEST"}, owner=True,
                           headers={"Origin": "https://evil.example"})[0] == 403
            assert request("POST", "/api/me/watchlist", {"ticker": "TEST"}, owner=True)[0] == 200
            assert request("POST", "/api/me/positions", {"ticker": "TEST", "amount_usd": 100,
                           "buy_date": "2026-10-15", "buy_price": 10}, owner=True)[0] == 200
            _, api_headers, _ = request("GET", "/api/auth/me", owner=True)
            assert api_headers["cache-control"] == "no-store"
            assert api_headers["x-frame-options"] == "DENY"
            assert "Strict-Transport-Security".lower() in api_headers
            assert request("POST", "/api/auth/register", {"email": "member@example.com",
                           "password": "A-long-member-password-123"})[0] == 201
            # A member cannot read the owner's position even with its valid session.
            _, member_headers, _ = request("POST", "/api/auth/login", {
                "email": "member@example.com", "password": "A-long-member-password-123"})
            member_cookie = member_headers["set-cookie"].split(";", 1)[0]
            status, _, raw = request("GET", "/api/me/positions/TEST", headers={"Cookie": member_cookie})
            assert status == 200 and json.loads(raw)["position"] is None
            assert request("POST", "/api/auth/password-reset/request", {"email": "unknown@example.com"})[0] == 204
            status, _, raw = request("GET", "/api/auth/status")
            assert status == 200 and json.loads(raw)["password_reset_available"] is False
            assert request("POST", "/api/auth/login", {"email": "x" * 1_100_000})[0] == 413
            seed = '''import asyncio
from app.persistence.db import session_scope, save_run
from app.schemas.research import ResearchResponse, ResearchReport, SECFindings, NewsFindings, MetricsFindings, InsiderFindings
from app.config import get_settings
async def main():
 p = ResearchResponse(ticker="TEST",sec=SECFindings(status="skipped"),news=NewsFindings(status="skipped"),metrics=MetricsFindings(status="ok",current_price=10),insider=InsiderFindings(status="skipped"),report=ResearchReport(ticker="TEST",recommendation="Buy",justification="Synthetic release-test fixture",confidence=70,company_overview="",financial_health=""))
 async for db in session_scope():
  await save_run(db,ticker="TEST",recommendation="Buy",justification="Synthetic release-test fixture",sentiment_score=None,payload=p.model_dump(),horizon_days=14,llm_model=get_settings().llm_model)
  break
asyncio.run(main())
'''
            run(compose + ["exec", "-T", "backend", "python", "-c", seed], stdout=subprocess.DEVNULL)
            status, headers, raw = request("GET", "/api/research/TEST/stream", owner=True)
            assert status == 200 and "text/event-stream" in headers["content-type"]
            assert "event: started" in raw and "event: completed" in raw and '"cached": true' in raw
            run(compose + ["exec", "-T", "backend", "python", "-m", "app.scripts.backup_sqlite",
                           "--output-dir", "/tmp/recovery"], stdout=subprocess.DEVNULL)
            run(compose + ["exec", "-T", "backend", "python", "-m", "app.scripts.backup_sqlite",
                           "--verify", "/tmp/recovery"], stdout=subprocess.DEVNULL)
            run(compose + ["restart", "backend"], stdout=subprocess.DEVNULL)
            run(compose + ["up", "--no-build", "--wait", "--wait-timeout", "120"], stdout=subprocess.DEVNULL)
            assert request("GET", "/api/auth/me", owner=True)[0] == 200
            status, _, raw = request("GET", "/api/me/positions/TEST", owner=True)
            assert status == 200 and json.loads(raw)["position"]["amount_usd"] == 100
            assert request("POST", "/api/auth/logout", owner=True)[0] == 204
            assert request("GET", "/api/auth/me", owner=True)[0] == 401
            print("PASS: production settings, healthy containers, TLS, secure cookies, bootstrap guard, host/origin/CSRF, user isolation, body cap, cached SSE, backup verification, restart persistence, and logout revocation")
        finally:
            # Only this freshly generated project's synthetic volume is removed.
            run(compose + ["down", "--volumes", "--remove-orphans"], stdout=subprocess.DEVNULL)


if __name__ == "__main__":
    main()
