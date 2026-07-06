# Security Policy

## Reporting a Vulnerability

Please report suspected vulnerabilities through the repository's private GitHub
Security Advisory flow. Do not include credentials, recovery codes, session
cookies, database dumps, or exploit details in a public issue.

Include the affected version or commit, reproduction steps, impact, and any
suggested mitigation. A maintainer should acknowledge the report before details
are disclosed publicly.

## Deployment Responsibility

Verdict is self-hosted software. Operators are responsible for TLS termination,
secret storage, backups, dependency updates, upstream API budgets, and access to
the host and database. See [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for the
production checklist.

Only the latest commit on the default branch receives security fixes.
