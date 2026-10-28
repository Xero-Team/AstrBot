# Web, Dashboard, and authentication hunting

## When to use

The target speaks HTTP or WebSocket: Dashboard API routes, login/session/TOTP,
step-up, API keys, CSRF origin checks, rate limiting, proxy trust, the unified
chat socket, raw file/SSE routes, or the Open API socket. Use it with the
hunting method and candidate gate in `hunting-prompt.md`; access control asks
whether a principal may perform an operation, this file asks whether HTTP or
identity plumbing confuses which principal, request, assurance level, or token
owns it.

Source map: `astrbot/dashboard/api/` (`router.py`, `auth.py`,
`authorization.py`, `webchat.py`, `open_api.py`, `files.py`, `logs.py`,
`plugin_page_assets.py`), `astrbot/dashboard/server.py`,
`astrbot/dashboard/services/auth_service.py`, `astrbot/core/auth/service.py`,
`astrbot/core/webchat/run_coordinator.py`,
`astrbot/dashboard/services/webchat_service.py`.

## Core discipline

- Framing and cache claims need two interpretations of the same request,
  response, or key. Name both components and the exact normalized value on each
  side. An ASGI app behind an unobserved proxy has little source-confirmable
  smuggling surface.
- For every credential, find the verification and every binding required for
  its role: issuer, audience, origin, session, principal, resource, assurance,
  expiry, and one-time state.
- `Host`, `Forwarded`, `X-Forwarded-*`, `Origin`, `Referer`, redirect targets,
  callback URLs, and request-derived URLs are trust decisions only when the
  deployment trusts them. The flag that decides is
  `dashboard.trust_proxy_headers` (default `false`).
- A missing header, cookie attribute, TOTP prompt, or rate limit is not a
  finding alone. Require an accepted invalid request, cross-principal impact,
  assurance downgrade, or credential disclosure.
- `confirmed` needs complete source evidence and a bounded local request/token
  test. Use `needs_validation` when proxy, IdP, browser, certificate, secret, or
  deployed configuration is required but not visible.

## Authentication and session classes

**Credential-source confusion.** A route accepts a bearer token, a cookie, or
an API key, and the strongest check is applied to only one source.
`require_scope` resolves API key → JWT bearer → cookie; `require_dashboard_
session_principal` requires bearer and cookie to name the same `sid`, username,
and account; `require_dashboard_control_plane_principal` requires both plus
CSRF origin for mutations. A route that mixes these dependencies, or accepts a
cookie mutation without the origin check, is a candidate.

**Stateless-token lifecycle.** Dashboard JWTs are HS256 with `sid`/`jti`, but
there is no server-side revocation list; logout clears the cookie and principal
re-validation catches disabled or renamed accounts. Check every privileged
route for principal re-validation and every fallback that skips it. Do not
report "JWT is stateless" by itself.

**Step-up binding.** `issue_step_up` stores only `sha256(secret)` and binds
subject, session, action, resource, context digest, and expiry;
`_consume_step_up` is single-use and must match all of them. Look for a route
that issues a step-up credential for a decision other than
`step_up_required`, a WebChat token that accepts another action, a token reused
across runs or sessions, or a high-risk mutation that skips the check.

**TOTP enrollment and recovery.** Pending factor rotation is session-bound;
a recovery code disables TOTP and revokes trusted devices; trusted-device
tokens hash the token and the current TOTP secret. Check a first factor that can
replace the second without fresh authentication, a cross-session enrollment
completion, a recovery path that leaves old devices valid, and a fallback that
accepts a stale factor.

**Password reset and account transition.** Verify token randomness, user/action
binding, expiry, one-time state, invalidation of prior sessions/tokens, and
delivery-URL trust. Different responses that only reveal public account
existence are not automatically a finding.

**API keys.** Compare the key hash lookup, active/expiry checks, scope
enforcement, and the principal it maps to. A publishable identifier is not a
secret; require a lower-trust reader or a resource the key should not reach.

## Request, proxy, and browser-session classes

**Trusted-proxy and client-IP derivation.** `_get_request_client_ip` uses
`X-Forwarded-For`/`X-Real-IP` only when trusted; the same flag gates external
origin derivation for CSRF. If a route reads forwarded metadata directly, or
the deployment trusts headers without overwriting them, the rate-limit key,
CSRF origin, or access log becomes attacker-influenced. Missing proxy hardening
on a loopback-only default is `needs_validation`, not a confirmed bypass.

**Rate-limit scope and bypass.** The limiter covers a fixed endpoint set and
keeps a bounded registry (10,000 entries, one-hour TTL). Check an expensive or
credential-checking route outside the set, a spoofable client key under a
trusted-proxy misconfiguration, and WebSocket paths that bypass the HTTP
middleware entirely. A bypass alone is hardening unless it enables guessing,
spend, or shared-resource exhaustion.

**CSRF and cookie scope.** The session cookie is `HttpOnly`, `SameSite=Strict`,
secure by default, and path-scoped to `/api/v1`; state-changing cookie requests
compare `Origin`. Check a mutation reachable without the origin check, a
cross-site subresource shape that same-site rules do not cover, login CSRF, and
a cookie selected differently by another component.

**Framing and cache.** Multiple `Content-Length`, `Transfer-Encoding`,
HTTP/2 downgrade, header normalization, and unkeyed cache inputs matter only if
the repository owns the parser or cache. A managed proxy outside source is
`needs_validation`.

**Response and error disclosure.** The envelope replaces validation details with
`Invalid request payload` and the catch-all uses `safe_error`. A raw route, a
plugin Action, or a service error that injects exception text, SQL, provider
messages, URLs, or tokens into a response is a candidate. Confirm the sensitive
value reaches a lower-trust reader.

## WebSocket and multiplexing classes

**Socket authentication.** The unified chat socket takes the JWT from
`Sec-WebSocket-Protocol`, accepts the socket, then closes with 1008 on an
invalid token before creating state. The Open API socket authenticates the API
key before trusting a caller-declared username or session. Check a handler that
reads `username`, `session_id`, `account_id`, or thread identity from the
message instead of the verified connection.

**Per-request isolation.** Each `send` creates a run keyed by `message_id`;
`create_run` enforces uniqueness, `dispatch` stamps the request id, and
`next_result` drops results from another request. Check a path that falls back
to "first socket for this session" for an unknown id, a shared busy flag, a
response emitted without request identity, an interrupt that cancels a sibling
run, and `agent_stats` or `run_started` delivered to the wrong run.

**Session ownership.** `_owns_chat_session` fails closed when the runtime DB is
unavailable, and the run's `umo` derives from the verified thread row, never
the client. A run that accepts a client-supplied `umo` or session id is a
cross-user candidate.

**Interrupt and replay.** Step-up tokens are filtered to instance tool actions,
length-capped, cleared after the run, and one-time at the core. Check replay
after completion, a token that survives an interrupt, and an interrupt that
leaves durable side effects.

## Raw routes and capability URLs

Routes that intentionally stay raw: static SPA shell, `/healthz`, `/readyz`,
`/metrics` (disabled by default), plugin page assets and SDK, plugin file
tickets, `/files/tokens/{token}`, `/data-files/download`, `/logs/live`,
`/logs/export`, chat SSE, and conversation export. Check that a raw route does
not require ambient credentials it cannot see, does not reflect user input, and
does not leak a token through URL, `Range`, error, or cache behavior. File
tickets reject ambient credentials, `Range`, and query params; static path
resolution rejects `..`, absolute paths, and `api/`; download responses force
attachment plus `nosniff` and degrade active types.

## Universal moves

- Walk issue → store → transmit → consume → refresh → revoke for every
  credential, challenge, and session. Compare normal, error, retry, migration,
  legacy, and account-switch paths.
- Enumerate every door to the same identity and every route to the same
  sensitive operation. The effective policy is the weakest parallel path.
- Diff router, dependency, middleware, and service normalization side by side.
  Feed identical bounded fixtures to each component locally.
- For recovery and account linking, draw the before/after account graph with
  the principal, proof, required assurance, callback binding, and revocation.

## Validation rules

1. Apply a source-visibility gate. Proxy chains, edge cache keys, IdP policy,
   certificate trust, browser cookie behavior, and deployed auth modes may be
   outside the repository. Record a precise `needs_validation`.
2. For framing and cache findings, name both components and the divergent
   parse or key, then prove cross-request, cross-user, or private-response
   impact with a local fixture.
3. For token, TOTP, recovery, API-key, and step-up findings, cite the
   verification line and the missing principal/session/resource/origin/
   audience/action/assurance binding. Prove the server accepts the invalid
   transition.
4. For CSRF, name the ambient credential, state-changing route, accepted
   cross-site request shape, browser policy, and missing effective check.
   Read-only actions and bearer-only routes do not qualify.
5. For WebSocket claims, cite the connection authentication, the message
   routing key, and the observable cross-run or cross-user effect. A client
   fallback that only affects its own view is not a server finding.
6. Verify framework defaults at the pinned version. Unknown version or
   configuration means `needs_validation`, not a lower-severity confirmed
   finding.
