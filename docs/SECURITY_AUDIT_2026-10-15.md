# Verdict security and deployment-readiness audit — 2026-10-15

**Result: substantial source remediation completed; public deployment still
requires operator decisions and external verification.** This is an evidence-based
code/configuration review, dependency/image audit and isolated release exercise,
not a guarantee that all vulnerabilities have been discovered. No public deployment,
real mail send, provider-permission change, data reset, or modification to the
existing local app was performed.

## Scope, baseline and how to read this note

- Baseline: `c8fca4045d3c807ba4c208e15831394e88dfa500`, checked against GitHub
  `main`. Its existing CI was green, not a failed deployment workflow.
- Changes are on `codex/security-deployment-audit` in an isolated worktree.
  No applicable `AGENTS.md` was present in that worktree or its ancestor paths.
- Reviewed app entry points, authentication, authorization, persistence,
  provider/network boundaries, LLM/tool handling, frontend output/links, proxy
  configuration, images/build contexts, CI, dependency manifests and operating
  instructions. Automated source searches supplemented focused manual review.
- High/medium/low labels below are contextual prioritization, not CVSS scores.
  “Fixed” means changed source plus the stated checks; it does not mean the old
  local containers have received the fix. Conditional misconfiguration risks,
  defense-in-depth work and functional/operational issues are labeled separately.
- Full package/advisory inventories (including low/unknown severities and
  repeated advisories across packages) are in
  [before](security-audit/container-advisories-before.csv) and
  [after](security-audit/container-advisories-after.csv). They include exact
  packages, versions, fixed versions, vendor status and primary advisory URLs.
  [Scan metadata](security-audit/scan-summary.json) records image/scan identities
  and artifact hashes. [Python](security-audit/pip-audit.json) and
  [npm](security-audit/npm-audit.json) retain complete dependency audit output.

## Confirmed code weaknesses remediated

### S01 — High — public registration could prevent first-owner setup — fixed

**Evidence:** `backend/app/routers/invites.py::register` accepted public password
signup without checking owner setup. Bootstrap checks the count of all users,
so an unauthenticated visitor could create the first member and leave bootstrap
unavailable. Google signup already had a first-account guard.

**Fix:** Password registration requires an existing owner before admitting any
member. Existing owner/user records and the unique owner-key protection remain.
**Validation:** A fresh database with public signup enabled returns 403 for
registration and still reports bootstrap required; integrated production test
then creates the owner successfully. Concurrent bootstrap remains protected by
`users.singleton_key` uniqueness.

### S02 — Medium — password invites were not redeemed atomically — fixed

**Evidence:** Password registration selected an unused invite, inserted the user,
then assigned `used_by/used_at` without a conditional database update. Concurrent
readers could both redeem a one-use invite. Google registration already used a
conditional update.

**Fix:** Claim the invite with `UPDATE ... WHERE used_at IS NULL AND expires_at >
now`, require one changed row, and roll back the new member if the claim loses.
**Validation:** Two concurrent registrations with different emails yield one 201
and one 401, with only the owner and one member in the database. Sequential
reuse, expiration and invite-mode regressions continue to pass.

### S03 — High — concurrent reset-token reuse could change a password twice — fixed

**Evidence:** `password_reset.py::confirm_password_reset` read a token before
changing the password and deleting tokens. Separate requests could both read
that token and proceed, violating single-use semantics.

**Fix:** Atomically delete/claim the unexpired token with `RETURNING` before
changing credentials; a losing request rolls back. Password updates, token/session
revocation and the completion audit event commit together. SQLAlchemy identity
synchronization is disabled for the conditional expiry comparison to avoid
SQLite naive/aware datetime errors.
**Validation:** Concurrent confirmations yield exactly one 204 and one 401;
existing full-flow tests verify old-password rejection, new-password acceptance,
current-session revocation and sequential token reuse rejection. Weak replacement
passwords do not consume the token.

### S04 — High — email-only Google linking enabled account pre-hijacking — fixed

**Evidence:** Public password signup does not verify email. Google login could
attach a verified Gmail/Workspace identity to that existing email while keeping
its password and sessions. Someone who pre-registered another person's email
would retain password access after the real email owner used Google.

**Fix:** Previously unlinked password accounts require proof of their existing
session **and** CSRF token, in addition to Google's authoritative email claim,
before linking. Signed-out matches return 409 and direct the user to the existing
sign-in method. Passwords and already linked Google identities are preserved.
**Validation:** Tests cover a pre-registered Gmail account, signed-out Workspace
matches, authorized linking, preserved password login, changed subjects,
wrong audiences/issuers/expiry, nonces, and inactive accounts.
**Product limitation:** There is no dedicated account-linking settings screen;
a signed-out user cannot silently combine two sign-in methods. This deliberate
restriction closes the unsafe automatic-link path.

### S05 — High — daily spending caps had races and uncovered endpoints — fixed

**Evidence:** Research checked counts of completed/saved runs before starting
work. Concurrent requests, failures and unsaved runs bypassed that accounting.
Day-trade/timing, chat, and direct filing ingest/query had no daily cap despite
LLM/embedding calls. Changing ticker/cache keys made this economically relevant.

**Fix:** New persistent `admission_counters` reserve global and personal slots
atomically, before those LLM/embedding operations. Failures/cancellation remain charged.
Cache hits stay free. Existing research rows seed first-use counters on upgrade.
Counter updates commit before provider work and roll back together on a personal
rejection. The caps remain a supported single-instance SQLite design.
**Validation:** Eight concurrent admissions against a two-operation cap admit
exactly two; subsequent work is denied even without a saved result. A personal
rejection does not consume a global slot. Existing cache, horizon, model-change,
per-user/global and failed-analysis tests pass.
**Limit:** A slot is an operation, not a token/dollar limit. Research may make many
calls; application caps cannot substitute for provider billing limits.

### S06 — Medium — short new passwords and IP-only abuse protection — fixed prospectively

**Evidence:** Six-character passwords were allowed despite password-only login.
IP throttling alone does not bound distributed attempts at one account; reset
requests could repeatedly mail one target from different IPs.

**Fix:** New/reset passwords require 15–128 characters; existing uppercase/digit
rules remain. Login accepts legacy passwords. Persistent per-email admission
limits cover password login (10/15 minutes) and reset (3/hour), independent of
IP, and both signup methods share a 100/day registration ceiling. Authenticated
account reads/writes are also bounded separately from IP limits.
**Validation:** New-password policy/UI fixtures, legacy short-password login,
normalized-case account throttling, public/invite registration and SMTP reset
flows pass.
**Limit/action:** Existing weak passwords are not forcibly changed. Encourage
long unique replacements; no MFA was reintroduced. Fixed windows allow bursts
near a boundary. Targeted throttling can temporarily affect a legitimate user;
recovery/Google methods and edge abuse controls matter.

### S07 — Medium — request and upstream work could exhaust resources — bounded

**Evidence:** nginx bounded bodies, but a direct backend request had no application
body cap. Research's graph deadline excluded auto-ingest; SSE and other provider
routes lacked a common full-request/concurrency limit. SEC response sizes and
embedding chunk counts were unrestricted.

**Fix:** ASGI body caps include chunked input; reject before parsing above 1 MiB.
An eight-request expensive-work cap rejects overflow rather than queueing it.
A whole-request deadline includes ingestion, retries and SSE. SEC responses stop
above 25 MiB decompressed; indexing stops above 2 million text characters/2,500
chunks. HTML parsing runs in a worker thread. SEC requests/retries are paced
below ten starts/second in the single supported event loop.
**Validation:** Chunked oversized bodies never reach the downstream parser;
concurrent overload produces 503 and timeout frees capacity. Production nginx
rejects >1 MiB; provider/SEC/chunking and SSE tests pass.
**Limits:** Already running synchronous threads cannot be forcibly killed by
async cancellation. Non-SEC provider responses are bounded primarily by their
timeouts, provider contracts and container memory. Volumetric/network attacks
still require an edge/host strategy; no destructive load test was run.

### S08 — Medium — workspace admission caps raced and some tables were unbounded — fixed

**Evidence:** Watchlist/alert/strategy caps read a count before inserting. Parallel
writes could exceed them. Position and verdict-watch creation lacked total caps;
chart levels had only a per-ticker cap. Infinite buy prices could reach stored
state/response serialization.

**Fix:** Serialize count/write operations through a no-data-change user-row lock;
apply per-account totals without deleting existing rows. Reject non-finite
position prices and bound them to the existing supported monetary range.
**Validation:** Two simultaneous additions to a 23-symbol watchlist produce one
success and one cap rejection; total remains 24. Non-finite prices return 422 and
leave no position. Existing ownership and cash-only/idempotent practice tests pass.
**Limit:** Records/audit history still consume disk over time; rate/cap controls
are not a storage-retention or monitoring service.

### S09 — Medium — exceptions/logged URLs could expose credentials or request values — fixed

**Evidence:** Provider failures logged raw exception strings, structured exception
formatting included SQL/provider exception messages, startup logged a DB URI,
and access logs included raw query strings. Provider credentials can occur in
query parameters or exception text; SQL exceptions can contain bound values.

**Fix:** Error extras log exception types instead of raw strings. Structured
tracebacks contain frame metadata/type without source lines or exception values;
configured credentials and credential query parameters are redacted. Startup
logs only the DB driver. Health config exposes only the custom provider hostname.
nginx/Gunicorn access logs omit query strings.
**Validation:** A log with a configured API key, arbitrary query token and
sensitive exception text contains none of those values. Existing normalized
provider-error/validation tests pass. Secret scans pass.
**Limits:** Operators control external edge/provider/monitoring logs; historical
logs were not read, purged or declared secret-free. Protect and rotate them.

### S10 — Medium — recovery links could travel in request URLs and SMTP configuration could be unsafe — fixed

**Evidence:** Reset tokens used a query parameter and remained in the browser URL
until form completion. SMTP without username and STARTTLS disabled was accepted
in production, sending the bearer recovery link without transport encryption.
The “delivered” audit flag was recorded before mail success was known.

**Fix:** New links use a fragment; the UI captures/removes it immediately while
keeping legacy query compatibility. Production SMTP requires verified TLS,
complete sender/public-origin configuration and consistent credentials. Implicit
TLS supports providers on 465. Post-response delivery removes SMTP timing from
the HTTP response path; delivery audit flags reflect actual success and failed
sends retire their token.
**Validation:** STARTTLS/implicit TLS verify server certificates; cleartext login
is refused. Failed mail produces no usable token and `delivered=false`. The
mocked reset end-to-end flow still revokes sessions. SMTP-unconfigured production
reports recovery unavailable and returns a generic 204 for requests.
**Limit/action:** Delivery is best effort, not a persistent queue. Real sender,
credentials, DNS policy and actual delivery still require the operator.

## Configuration weaknesses and defense-in-depth work

| ID / priority / status | Evidence and change | Validation / remaining condition |
| --- | --- | --- |
| H01 / Medium / fixed | Production guard compared proxy trust entries to literal `0.0.0.0/0`/`::/0`; a noncanonical CIDR like `1.2.3.4/0` parsed as global trust. Now parses networks, rejects prefix zero and malformed entries. | Regression covers noncanonical routes and invalid CIDRs. Split supernets or overly broad valid ranges still need operator review. |
| H02 / Medium / fixed | Malformed forwarded hops could become arbitrary limiter keys. Resolution now stops at that hop and uses the actual peer rather than trusting a prefix or returning arbitrary text. | Trusted/untrusted peers, spoofed prefixes, chains, bracketed IPv6 and malformed values tested. Broad private-network trust remains a documented deployment choice, not proof that every private peer is trustworthy. |
| H03 / Medium / fixed | Production accepted HTTP/empty/path-bearing CORS entries and unsafe public/provider URLs. Validation now requires explicit HTTPS origins/hosts and a matching configured recovery origin, without URL userinfo/query/fragment. | Parameterized invalid configuration cases pass. A correctly formatted but wrong domain is still an operator error. |
| H04 / Medium / fixed | User/provider/model citation URLs were rendered without a scheme boundary. React text escaping and CSP already helped, but were not URL validation. New helper allows only HTTP(S), rejects userinfo/relative/malformed URLs. | Seven URL tests and frontend build pass. No CSP bypass or working script execution was demonstrated; this is defense in depth. Ordinary HTTPS destinations can still be misleading. |
| H05 / High conditional exposure / fixed | Backend Docker context did not exclude DB/data directories or arbitrary `.env.*` variants; `COPY . .` could bake local sensitive files into an image. Git ignores are not Docker ignores. | Both build contexts now exclude env variants, DB/WAL/SQLite files, data, private keys and Git metadata. No claim that a previously built image contained real credentials; old image layers/registries require operator review if sensitive files were present. |
| H06 / Low / fixed | Origin/host errors and centralized 500 responses could bypass the inner security-header middleware. Cross-site fetch metadata was ignored if Origin was absent. | Headers wrap all responses; cross-site writes fail. Host/origin/error-header tests and production smoke pass. Non-browser clients may omit Origin; authenticated writes still require CSRF. |
| H07 / Medium / hardened | Model/tool/doc inputs can carry prompt injection; tool arguments were assumed to be a JSON object and any requested function name was effectively treated as filing search. | System prompts mark supplied material untrusted. Only `search_filing` is executable, query type/length is bounded, and malformed arguments fall back safely. Tools cannot browse arbitrary URLs, read files or trade. Prompt instructions cannot guarantee semantic safety; grounded output remains fallible. |
| H08 / Medium / fixed | CI actions/base tags were mutable and Python transitive dependencies resolved anew. | Inspected top-level action/base manifest digests pinned; Linux runtime transitive versions constrained. Composite actions may have their own dependencies, which still require vendor/update review. Dependabot remains configured. Distribution updates intentionally refresh at build time; retain reviewed release images, not only source hashes. |
| H09 / Medium / fixed | `.gitleaks.toml` excluded the entire example env file, allowing a real pasted credential to bypass scanning. | Allowlist now matches only documented placeholder/boolean false-positive text in that file. Full Git history and staged changes scanned with redaction. |

Two additional small boundary defects were fixed in the final review:

- **H10 / Low:** non-ASCII strings passed to `secrets.compare_digest` could raise
  a TypeError instead of rejecting a bad bootstrap/CSRF/Google nonce. Comparisons
  now use UTF-8 bytes; a regression verifies a malformed CSRF header returns 403.
- **H11 / High conditional log exposure:** Pydantic settings startup errors could
  include the entire configuration input before app log redaction was installed.
  `hide_input_in_errors=True` prevents that dump; a synthetic secret is absent
  from a deliberately failed production configuration error. CORS origins also
  normalize trailing slashes so safe-but-noncanonical settings do not break
  browser writes/recovery-origin matching.

## Deployment and maintenance defects (not mislabeled as vulnerabilities)

| ID / priority / status | Finding, implemented change and evidence | Remaining operator action |
| --- | --- | --- |
| O01 / High readiness / fixed | Existing frontend probe followed the local 307 redirect to `localhost`, BusyBox chose `::1`, and nginx only listened on IPv4. Added IPv4 `/healthz`, exempt from that redirect, in both Dockerfile and Compose. | Roll the reviewed image into the original local stack deliberately; it is still running the old unhealthy image. Local Google redirect remains verified. |
| O02 / High readiness / fixed | Restricting production `ALLOWED_HOSTS` to the actual domain also rejected container-local backend health checks. A narrowly scoped loopback-only `/health` host exemption and numeric probe fix production startup. | Public/custom-host routes remain checked; never expose backend directly. Production-only host checks were exercised, not just dev health. |
| O03 / High readiness / fixed | Base Compose lets `backend/.env` override root `.env`. A developer file could silently defeat root production settings. | Use the new explicit production overlay and external env path. It forces secure mode and excludes developer env overrides. Do not run a secrets-expanded Compose dump in logs. |
| O04 / Medium readiness / fixed | Bundled nginx overwrote edge HTTPS protocol with its internal HTTP scheme and dropped the Host port. | Preserve edge HTTPS protocol and full Host; disable Gunicorn forwarded rewriting and document edge overwrite/append requirements. Real TLS/forwarding tested through a disposable edge. Actual public edge still unconfigured/unverified. |
| O05 / High recovery / tooling completed | Previous backup instructions only said to back up a volume, with no WAL-safe procedure/restore evidence. Added snapshot/verify CLI with consistent SQLite backup API, hashes, integrity and private permissions. | Schedule encrypted off-host backups; choose retention/RPO/RTO and exercise host-loss restoration. No live-user backup or restore was performed. |
| O06 / Medium readiness / fixed | Readiness omitted DB access, could be repeatedly called to probe providers, left a temporary LLM client open, and did synchronous Pinecone work on the event loop. | Add DB check/throttle, close probe client, offload Pinecone call. Liveness remains deliberately cheap. No credential-free synthetic test can establish live provider readiness. |
| O07 / Medium maintenance / fixed | Auth cleanup depended on the alerts worker being enabled, and expired quote previews lacked periodic cleanup. | Hourly worker cleans expired authentication and quote previews. Historical users/trades/research/audits are preserved. Multiple replicas still need coordinated workers. |
| O08 / Medium operations / bounded | Containers had PID/capability/read-only controls, but no memory/CPU/log-rotation bounds. Dev overlay exposed ports on all host interfaces. | Added tunable memory/CPU limits, rotating Docker logs, loopback dev ports and private runtime umask. Measure capacity and monitor persistent-volume growth; no real load benchmark or disk-full incident exercise was run. |
| O09 / High release gate / fixed | CI built images but did not scan their OS packages or exercise production Compose/TLS/persistence. | CI now retains full scans, fails on fixable high/critical findings, and runs isolated release verification. No auto-deploy/auto-merge added. Final remote review also replaced deprecated Node 20 actions with inspected Node 24 releases, disabled checkout credential persistence and pinned the runner to Ubuntu 24.04 before the announced Ubuntu 26 migration. |
| O10 / High maintenance / partially remediated | Bases used Python 3.13.13/nginx 1.31.1 and stale OS packages. Upgraded to Python 3.13.16/nginx 1.31.7, applied distribution updates, removed backend curl/dependency tree and runtime pip, pinned base digests. | Current Debian unfixed advisories remain; see exact CSV inventory and next section. nginx's own upstream security releases were checked separately because a binary not managed by APK may escape package scanners. |
| O11 / Low performance / noted | Frontend production JS is about 581 kB (173 kB gzip), triggering Vite's >500 kB advisory. | Build passes. This is a performance warning, not a security finding; evaluate code splitting against actual load measurements. |

## Dependencies and remaining container advisories

Current npm audit and pip-audit report **zero known vulnerabilities** in their
resolved dependency graphs. This is time-dependent advisory coverage, not proof
of absence of vulnerabilities or malicious packages. Python runtime transitive
versions are now recorded in `backend/constraints.txt`; source changes must
refresh constraints and rerun audits together.

The initial local runtime-image scans found **668 package/advisory entries**:
backend 538 (3 critical, 106 high, 212 medium, 214 low, 3 unknown), frontend 130
(40 high, 62 medium, 26 low, 2 unknown). After updates/removal the frontend reports
zero; backend reports **164: 44 high, 58 medium, 61 low, 1 unknown, zero critical**.
All remaining entries have no fixed version for the current stable distribution
in the scanner/vendor feed. Upstream/testing releases can have fixes that are
not yet available as supported trixie packages.
The inventory lists each of them, not just an aggregate or severity cutoff.
Repeated CVEs across related binary packages count as multiple entries.

These findings were **not silently suppressed**. No application-specific exploit
was established for every package advisory. Some concern local utilities or
features not exercised by this app, and non-root/read-only/capability restrictions
reduce several attack paths. That is not sufficient to declare all 44 high
findings harmless. Before public release, review their primary Debian advisories,
confirm reachable paths in the exact deployed architecture, update when fixes
arrive, and make an explicit risk/hosting decision. CI only automatically rejects
currently fixable high/critical entries; its green result is not risk acceptance
for the rest. The full scan artifacts remain visible.

The native local scans use Linux ARM64 images. CI builds/scans Linux AMD64.
Architecture-specific inventories can differ; the CI artifacts are authoritative
for its own images. Published deployment images must be scanned separately.

### Primary-source review of the eight unique remaining high CVEs

The 44 high package matches map to these **eight** CVEs. Debian's tracker was
checked directly on 2026-10-15 and marks their trixie source packages vulnerable,
with no stable fix currently available (several are categorized as minor/no-DSA
or postponed by Debian). Scanner severity and application reachability are
different questions. The runtime runs as UID 10001; the supported Compose setup
also drops all capabilities, prevents privilege gain and makes the root filesystem
read-only. The app has no request-driven shell execution, mounting, ACL-management,
Perl archive extraction or uploaded terminfo surface.

| Advisory / source package | Relevant precondition and current evidence | Status |
| --- | --- | --- |
| [CVE-2025-69720](https://security-tracker.debian.org/tracker/CVE-2025-69720) / ncurses | Overflow in `infocmp` analysis; the binary exists, but the app does not execute it or accept terminfo uploads. | Stable fix unavailable; no reviewed app route reaches this CLI. |
| [CVE-2026-16742](https://security-tracker.debian.org/tracker/CVE-2026-16742) / systemd | Requires a locally logged-in homed-managed user and systemd-homed. The binary is absent at `/usr/lib/systemd/systemd-homed`; the container runs Gunicorn, not systemd. | Library/source-package match; described service precondition absent. |
| [CVE-2026-54369](https://security-tracker.debian.org/tracker/CVE-2026-54369) / acl | A privileged caller follows attacker-controlled paths through pathname ACL functions. No reviewed app code manages ACLs or calls those functions. | Stable ABI update pending; no application exploit established. |
| [CVE-2026-76642](https://security-tracker.debian.org/tracker/CVE-2026-76642) / util-linux | Privileged mount helper/post-hook path. Mount binaries exist, but no application shell/mount path or required privilege is provided by supported Compose. | Stable fix unavailable; privileges restricted. |
| [CVE-2026-78408](https://security-tracker.debian.org/tracker/CVE-2026-78408) / util-linux | A privileged operator invokes `nsenter --join-cgroup` on an attacker-controlled target. `nsenter` exists but the app never calls it. | Stable fix unavailable; operator should not add this privileged workflow. |
| [CVE-2026-78409](https://security-tracker.debian.org/tracker/CVE-2026-78409) / util-linux | Local fstab-authorized `X-mount.subdir` operation on relevant newer kernels. No mount/fstab editing endpoint or mount capability is exposed. | Stable fix unavailable; deployment/host changes could alter preconditions. |
| [CVE-2026-78410](https://security-tracker.debian.org/tracker/CVE-2026-78410) / util-linux | Restricted privileged bind mounts with attacker-controlled source ancestors and X-mount hooks. No reviewed app path provides that operation. | Stable fix unavailable; capability/no-new-privileges controls retained. |
| [CVE-2026-9538](https://security-tracker.debian.org/tracker/CVE-2026-9538) / perl | Memory exhaustion in Perl `Archive::Tar` parsing. The module is absent at both conventional 5.40/5.40.1 paths, and the app has no Perl archive-processing path. | Source-package advisory; described module/use preconditions not found. |

These are bounded reachability observations, **not** VEX certification, exploit
proofs, or authorization to accept risk. They do not cover an arbitrary-code
compromise, unexpected native-library behavior, or a different deployment.
Mixing unstable system packages into stable Debian solely to remove scanner
entries would add compatibility/update risk; this audit kept supported stable
updates and retained every advisory for review.

## Controls verified without needing a new fix

- Passwords use Argon2id (19 MiB, two iterations, one lane), random salts and
  rehash-on-login. Absent/Google-only password hashes use a timing dummy that
  cannot authenticate. Login failure messages do not identify existing users.
- Sessions, invites, reset tokens and Google challenges store SHA-256 digests of
  high-entropy random tokens; plaintext session tokens remain HttpOnly cookies.
  Session lookup checks active user, idle timeout and absolute expiry.
- Unsafe authenticated methods require constant-time CSRF-token comparison;
  cookies are same-site strict, and configured browser origins are checked.
  CORS is not treated as authorization. Owner-only invite operations enforce role.
- All business routers are authenticated. Watchlists, alerts, levels, positions,
  strategies, practice quotes/trades/accounts and notes scope reads/writes to
  authenticated user IDs. Practice spending/close operations use conditional
  writes and quote idempotency; this audit preserves those accounting contracts.
- Research history, cached research and scoreboard are intentionally communal.
  They are not private user journals. No account/session tokens are included in
  report envelopes. Incomplete issued predictions keep their original time and
  horizon; failed/no-prediction attempts do not become fabricated Hold/50% results.
- SQL queries use bound SQLAlchemy/SQLite parameters. Raw migration SQL uses
  static identifiers/statements. No request-driven SQL interpreter, shell exec,
  pickle deserialization, arbitrary file upload/download or user-selected backend
  network URL was found in the reviewed route surface.
- SEC/market/news endpoints are fixed provider URLs; ticker inputs do not select
  a host. XML uses `defusedxml`; HTML becomes plain text. The stock-directory
  downloader follows redirects from fixed Nasdaq sources, not arbitrary client
  URLs. Administrative custom provider endpoints remain an operator trust boundary.
- React renders report/chat text without `dangerouslySetInnerHTML` or a raw HTML
  Markdown renderer. Dynamic evidence links now have an explicit URL boundary.
  CSP restricts scripts/frames to the app and Google GIS; inline styles remain
  allowed for GIS/chart rendering. There is no general inline-script permission.
- Provider keys are backend configuration, not Vite build variables. `.env` files
  are ignored; ignored env variants/build data are now hardened further. Non-root
  runtime users, internal backend networking, read-only mounts, tmpfs, capability
  drops and no-new-privileges were retained and exercised by the smoke stack.
- Google verification uses the official verifier for signature, issuer, audience
  and expiry; email verification and nonce binding are required. Nonces are
  atomically consumed. No access/refresh token or client secret is needed for the
  GIS popup ID-token flow. Real-origin success remains an external test.

## External blockers, residual risks and minute operating details

1. **No chosen production target/domain/certificate.** The current developer app
   is not a public-production instance. Confirm DNS, certificate renewal, HTTP to
   HTTPS redirect, host firewall, ingress reachability, Google authorized origin,
   trusted proxy addresses and host/Docker updates. The local synthetic certificate
   is explicitly trusted only by the test client and is not a public certificate.
2. **Unfixed OS advisory review.** The 164 backend entries remain open vendor
   findings, not completed fixes. An independent penetration test/fuzzing exercise
   and actual traffic/load study were not performed.
3. **Recovery provider not configured.** Supply real SMTP host/port/auth/sender,
   public origin and email DNS policy; prove actual mail delivery. The code safely
   reports recovery unavailable without SMTP, but this does not give existing
   password-only users a working recovery channel. Decide whether to launch
   without it. Do not invent credentials or reset current accounts.
4. **Third-party data rights and provider accounts.** NewsAPI's Developer plan
   explicitly excludes staging/production, including internal production. Its
   configured status is not proof of a production subscription. Leave it disabled
   or obtain appropriate rights. Review Yahoo/yfinance, Nasdaq, SEC and optional
   feed terms, redistribution/caching restrictions, quotas and model billing.
   No subscriptions, permissions, payments or provider budgets were changed.
5. **Open signup has a deliberate abuse tradeoff.** There is no email verification
   or CAPTCHA. Signup emails are self-asserted identities; duplicate registration
   returns 409 and reveals availability. Google linking no longer trusts those
   claims. Global registration/provider budgets bound activity, but attackers can
   use up shared allowances. For a small controlled launch, invite-only mode is
   already available; public launch may need provider-backed verification/edge
   abuse controls. No unsolicited external vendor was installed.
6. **Single-worker/host constraints remain.** SQLite WAL, in-memory endpoint limits,
   local caches and background workers are supported for one process. Persistent
   counters fix daily accounting, not distributed worker coordination. Redis alone
   does not make scheduled alerts/grading or all caches distributed-safe. A DB/
   coordination migration should follow an actual scaling need.
7. **Persistence must stay writable and private.** Preserve the named volume and
   UID 10001 ownership. Do not use `down --volumes` on real data. SQLite WAL/SHM
   sidecars matter for live copies; online snapshots avoid that hazard. A volume
   is not an off-host backup. Secrets in environment/Docker metadata remain
   visible to trusted Docker/host administrators by design.
8. **Recovery and retention operations are not scheduled here.** Choose encrypted
   off-host storage, backup schedule/retention, alert recipients, disk thresholds,
   RPO/RTO and a full restoration drill. The source CLI refuses overwrites and
   validates snapshots; it cannot supply those external operating arrangements.
   Audit/research/user history is preserved and grows over time.
9. **Log/metadata privacy.** IPs and user agents are audited. Restrict access,
   define retention/notification policy, and avoid sensitive URL logging at any
   edge/APM/mail service. Request IDs are sanitized/bounded correlation labels,
   not authentication or proof of a unique client. No historic log purge was done.
10. **LLM trust remains bounded, not solved.** External filings/headlines and
    client-supplied chat context are untrusted. The tool has no arbitrary URL,
    file, shell or trading capability, but prompt injection can still affect the
    financial narrative. The app is a research/simulation tool and does not submit
    trades. User chat/report data can be sent to the configured provider; review
    provider retention and the app's published privacy/financial disclosures for
    the intended deployment. No legal/compliance certification is asserted.
11. **Monitoring remains an operator task.** Liveness is not upstream readiness;
    provider readiness is not billing headroom, mail deliverability or database
    recovery proof. Monitor certificate/backup age, DB disk, 429/5xx and login
    patterns, mail failures, model changes and provider invoices/quotas. Configure
    an incident response/credential-rotation procedure. No third-party messages
    or alerts were sent.
12. **Browser compatibility remains empirical.** Synthetic HTTP/TLS checks and
    frontend unit/build tests do not replace real Chrome/Safari Google popup,
    mobile, CSP and SSE testing on the final origin. Legacy reset query links
    may exist in historic mail/logs; new fragment links prevent new server URL
    exposure. The UI removes a link token early, but cannot erase prior logs or
    a user's already copied URL.
13. **Updates need ongoing work.** Pinned manifests/actions/constraints prevent
    silent base/dependency movement; they also require reviewed updates. OS
    repository upgrades can change build outputs between releases. Retain image
    identities, scan reports and a rollback image/config/data plan. CI advisory
    results age immediately and may vary by architecture/scanner coverage.

## Validation and runtime separation

Validation commands and their current results are recorded in
[validation.json](security-audit/validation.json); The [draft PR](https://github.com/Yameen05/Verdict/pull/46) Checks tab provides
the remote CI results for its exact revision. The meaningful local release test
uses only synthetic accounts and fresh disposable volumes, with no real provider
keys and no outbound mail. It tests the reviewed source/image rather than the
user's existing app database.

The original local containers were observed as `verdict-backend-1` healthy and
`verdict-frontend-1` unhealthy on loopback port 8080. The failure was reproduced
with the probe redirect/IPv6 trace. They were not recreated/restarted by this
audit. Their developer settings and user data were not copied into this worktree.
Applying the changes to that stack is a separate deliberate rollout after review.

## Current primary references

- [OWASP authentication guidance](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html)
  and [password recovery guidance](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html)
  informed the new-password threshold and single-use/recovery-response boundaries.
- [OWASP prompt injection guidance](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html)
  supports treating model-facing documents/tool outputs as untrusted; it does not
  establish that prompt-only mitigations eliminate injection.
- [nginx proxy directives](https://nginx.org/en/docs/http/ngx_http_proxy_module.html),
  [real-IP trust](https://nginx.org/en/docs/http/ngx_http_realip_module.html), and
  [security advisories](https://nginx.org/en/security_advisories.html) were checked.
  [nginx 1.31.7 security release](https://blog.nginx.org/blog/nginx-1-31-7-native-geoip2-support-http-2-priorities-and-quic-improvements)
  and [Python 3.13.16 security release](https://blog.python.org/2026/10/python-31022-31117/)
  justify updating maintained runtimes even where package scanners miss binaries.
- [Compose environment precedence](https://docs.docker.com/compose/how-tos/environment-variables/envvars-precedence/)
  explains why a CLI env file alone does not remove service developer overrides.
- [SQLite online backup](https://sqlite.org/backup.html) supports consistent live
  snapshots rather than copying only a database file with an active WAL.
- [SEC fair access](https://www.sec.gov/search-filings/edgar-search-assistance/accessing-edgar-data)
  sets the aggregate ten-requests/second boundary and contact User-Agent requirement.
- [NewsAPI permitted plans](https://newsapi.org/pricing) establishes the production
  subscription limitation; account entitlement was not inferred from a key.

### Source-location index

The generated index below gives exact locations in this final change set. Symbol
names above describe the relevant behavior; tests provide reproduction evidence.

- [`backend/app/routers/invites.py:149`](../backend/app/routers/invites.py#L149) — `async def register`
- [`backend/app/routers/invites.py:194`](../backend/app/routers/invites.py#L194) — `redeemed =`
- [`backend/app/routers/auth.py:61`](../backend/app/routers/auth.py#L61) — `async def bootstrap`
- [`backend/app/routers/auth.py:101`](../backend/app/routers/auth.py#L101) — `async def login`
- [`backend/app/routers/password_reset.py:71`](../backend/app/routers/password_reset.py#L71) — `async def request_password_reset`
- [`backend/app/routers/password_reset.py:82`](../backend/app/routers/password_reset.py#L82) — `async def _deliver_reset`
- [`backend/app/routers/password_reset.py:142`](../backend/app/routers/password_reset.py#L142) — `async def confirm_password_reset`
- [`backend/app/routers/password_reset.py:164`](../backend/app/routers/password_reset.py#L164) — `consumed =`
- [`backend/app/routers/google_auth.py:86`](../backend/app/routers/google_auth.py#L86) — `async def google_login`
- [`backend/app/routers/google_auth.py:139`](../backend/app/routers/google_auth.py#L139) — `same_account =`
- [`backend/app/services/budgets.py:21`](../backend/app/services/budgets.py#L21) — `class AdmissionCounter`
- [`backend/app/services/budgets.py:28`](../backend/app/services/budgets.py#L28) — `async def _claim`
- [`backend/app/services/budgets.py:39`](../backend/app/services/budgets.py#L39) — `async def reserve_provider_operation`
- [`backend/app/services/budgets.py:65`](../backend/app/services/budgets.py#L65) — `async def reserve_auth_attempt`
- [`backend/app/security.py:35`](../backend/app/security.py#L35) — `PASSWORD_HASHER =`
- [`backend/app/security.py:70`](../backend/app/security.py#L70) — `def validate_password`
- [`backend/app/security.py:186`](../backend/app/security.py#L186) — `async def get_auth_context`
- [`backend/app/security.py:228`](../backend/app/security.py#L228) — `def verify_csrf`
- [`backend/app/security.py:236`](../backend/app/security.py#L236) — `async def require_authenticated`
- [`backend/app/resource_limits.py:14`](../backend/app/resource_limits.py#L14) — `class ResourceLimitsMiddleware`
- [`backend/app/config.py:11`](../backend/app/config.py#L11) — `model_config =`
- [`backend/app/config.py:243`](../backend/app/config.py#L243) — `def validate_production_security`
- [`backend/app/netaddr.py:69`](../backend/app/netaddr.py#L69) — `def client_ip`
- [`backend/app/middleware.py:74`](../backend/app/middleware.py#L74) — `class OriginProtectionMiddleware`
- [`backend/app/middleware.py:97`](../backend/app/middleware.py#L97) — `class SecurityHeadersMiddleware`
- [`backend/app/middleware.py:135`](../backend/app/middleware.py#L135) — `class DeploymentHostMiddleware`
- [`backend/app/observability/logging.py:40`](../backend/app/observability/logging.py#L40) — `class JSONFormatter`
- [`backend/app/routers/ask.py:222`](../backend/app/routers/ask.py#L222) — `async def ask`
- [`backend/app/routers/ask.py:290`](../backend/app/routers/ask.py#L290) — `assistant_message =`
- [`backend/app/routers/health.py:84`](../backend/app/routers/health.py#L84) — `async def _check_database`
- [`backend/app/routers/health.py:95`](../backend/app/routers/health.py#L95) — `async def ready`
- [`backend/app/routers/user_state.py:35`](../backend/app/routers/user_state.py#L35) — `async def lock_user_state`
- [`backend/app/routers/user_state.py:41`](../backend/app/routers/user_state.py#L41) — `async def cap_rows`
- [`backend/app/routers/user_state.py:91`](../backend/app/routers/user_state.py#L91) — `class PositionBody`
- [`backend/app/routers/practice.py:99`](../backend/app/routers/practice.py#L99) — `async def save_strategy`
- [`backend/app/routers/practice.py:308`](../backend/app/routers/practice.py#L308) — `async def place`
- [`backend/app/persistence/db.py:244`](../backend/app/persistence/db.py#L244) — `def get_engine`
- [`backend/app/persistence/db.py:265`](../backend/app/persistence/db.py#L265) — `async def init_db`
- [`backend/app/persistence/db.py:279`](../backend/app/persistence/db.py#L279) — `def _migrate_legacy_schema`
- [`backend/app/services/sec_client.py:30`](../backend/app/services/sec_client.py#L30) — `async def _pace_sec_request`
- [`backend/app/services/sec_client.py:44`](../backend/app/services/sec_client.py#L44) — `async def get_with_retry`
- [`backend/app/services/chunker.py:43`](../backend/app/services/chunker.py#L43) — `def chunk_filing`
- [`backend/app/services/mailer.py:26`](../backend/app/services/mailer.py#L26) — `def send_email`
- [`backend/app/services/maintenance.py:16`](../backend/app/services/maintenance.py#L16) — `async def clean_expired`
- [`backend/app/scripts/backup_sqlite.py:24`](../backend/app/scripts/backup_sqlite.py#L24) — `def snapshot`
- [`backend/app/scripts/backup_sqlite.py:50`](../backend/app/scripts/backup_sqlite.py#L50) — `def verify`
- [`frontend/src/components/AuthGate.tsx:36`](../frontend/src/components/AuthGate.tsx#L36) — `const [resetToken`
- [`frontend/src/components/AuthGate.tsx:49`](../frontend/src/components/AuthGate.tsx#L49) — `if (resetToken)`
- [`frontend/src/lib/safeUrl.ts:2`](../frontend/src/lib/safeUrl.ts#L2) — `export function safeExternalUrl`
- [`frontend/nginx.conf:3`](../frontend/nginx.conf#L3) — `map $http_x_forwarded_proto`
- [`frontend/nginx.conf:47`](../frontend/nginx.conf#L47) — `location = /healthz`
- [`frontend/nginx.conf:66`](../frontend/nginx.conf#L66) — `proxy_set_header X-Forwarded-Proto`
- [`backend/Dockerfile:4`](../backend/Dockerfile#L4) — `FROM python`
- [`backend/Dockerfile:62`](../backend/Dockerfile#L62) — `CMD ["gunicorn"`
- [`frontend/Dockerfile:15`](../frontend/Dockerfile#L15) — `FROM nginx`
- [`frontend/Dockerfile:18`](../frontend/Dockerfile#L18) — `RUN apk`
- [`docker-compose.yml:27`](../docker-compose.yml#L27) — `mem_limit:`
- [`docker-compose.yml:34`](../docker-compose.yml#L34) — `healthcheck:`
- [`docker-compose.production.yml:3`](../docker-compose.production.yml#L3) — `services:`
- [`.github/workflows/ci.yml:126`](../.github/workflows/ci.yml#L126) — `Scan backend runtime image`
- [`.github/workflows/ci.yml:155`](../.github/workflows/ci.yml#L155) — `Integrated production smoke test`
- [`scripts/verify_release.py:31`](../scripts/verify_release.py#L31) — `def main`
- [`backend/app/tests/test_security_remediation.py:56`](../backend/app/tests/test_security_remediation.py#L56) — `async def test_daily_admission`
- [`backend/app/tests/test_security_remediation.py:83`](../backend/app/tests/test_security_remediation.py#L83) — `async def test_concurrent_reset`
- [`backend/app/tests/test_security_remediation.py:101`](../backend/app/tests/test_security_remediation.py#L101) — `async def test_concurrent_invite`
- [`backend/app/tests/test_security_remediation.py:186`](../backend/app/tests/test_security_remediation.py#L186) — `async def test_watchlist_cap`
- [`backend/app/tests/test_security_remediation.py:227`](../backend/app/tests/test_security_remediation.py#L227) — `def test_startup_validation`
- [`backend/app/tests/test_google_auth.py:260`](../backend/app/tests/test_google_auth.py#L260) — `def test_google_cannot_attach`
- [`backend/app/tests/test_research_ask.py:378`](../backend/app/tests/test_research_ask.py#L378) — `def test_tool_arguments`
- [`backend/app/tests/test_backup.py:8`](../backend/app/tests/test_backup.py#L8) — `def test_online_wal_backup`
- [`backend/app/tests/test_mailer.py:112`](../backend/app/tests/test_mailer.py#L112) — `def test_implicit_tls`
- [`backend/app/tests/test_password_reset.py:183`](../backend/app/tests/test_password_reset.py#L183) — `async def test_failed_delivery`
- [`frontend/src/lib/safeUrl.test.ts:4`](../frontend/src/lib/safeUrl.test.ts#L4) — `describe(`
