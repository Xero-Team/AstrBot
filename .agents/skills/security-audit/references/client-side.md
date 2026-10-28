# Client-side and Dashboard browser hunting

## When to use

Trust decisions or untrusted rendering happen in a browser: the Dashboard SPA,
plugin Dashboard pages, embedded webviews, service workers, browser storage,
cross-window messaging, CORS, WebSockets, or DOM rendering. Browser-only
sources the server never sees include URL fragments, `window.name`,
`postMessage`, and cached content.

Use it with `web-and-dashboard.md` for server-side sessions and CSRF, and
`agent-and-llm.md` when model output reaches a renderer.

Source map: `dashboard/src/components/`, `dashboard/src/views/extension/`,
`dashboard/src/utils/`, `dashboard/src/stores/`, `dashboard/src/router/`,
`dashboard/src/api/`, `astrbot/dashboard/plugin_page_sdk.js`,
`astrbot/dashboard/services/plugin_page_session_service.py`.

## Core discipline

- A client-side candidate needs a controllable source and an executing or
  disclosing sink. Name both and show attacker-influenced data reaching the
  sink.
- Impact must reach a victim's session, another origin, or shared persistence.
  Self-injection and disclosure of the attacker's own data are not findings.
- Framework escaping, DOMPurify, browser same-origin policy, CSP, COOP/CORP,
  iframe sandboxing, service-worker scope, and `noopener` defaults are real
  controls. Verify them before assigning impact.
- Browser storage is shared by origin and may outlive login state. Identify who
  writes, who reads, and which account switch or logout clears each record.
- `confirmed` needs a complete source path plus bounded local browser evidence.
  `needs_validation` when renderer, extension permission, deployed header, or
  browser-version behavior is required but unavailable.

## DOM and object-state classes

**DOM-based XSS.** Trace `location` fields, `document.referrer`, `window.name`,
message data, storage, and server/model content into `innerHTML`, `outerHTML`,
`document.write`, string-evaluating APIs, executable URLs, and framework escape
hatches. Every current `v-html` sink sanitizes with DOMPurify
(`ReadmeDialog.vue`, `PluginDetailPage.vue`, `AstrBotConfigV4.vue`,
`IPythonToolBlock.vue`, `ProjectView.vue`, `ConversationHistoryPreview.vue`).
A missing sanitizer, a weakened allowlist, a sanitize-then-reparse gap, or a
new sink is a candidate. Framework `{{ }}` escaping is not XSS.

**DOM clobbering.** Attacker-injected `id` or `name` attributes shadow a global,
form property, config object, or initialization flag later trusted by code.
Require both a markup path that preserves the attribute and a security-relevant
use of the clobbered value.

**Prototype pollution and gadget chain.** An attacker-controlled key reaches a
recursive write such as deep merge or path assignment, then a reachable gadget
consumes the polluted property to change authorization, execution, navigation,
or rendering. `JSON.parse`, a shallow copy, or pollution without a gadget is not
enough.

## Cross-origin and extension classes

**`postMessage` origin and source trust.** A handler performs a sensitive action
with `event.data` without an exact origin allowlist and, where frames share an
origin, the expected `event.source`. The plugin page host accepts `ready` only
from `event.source === iframe.contentWindow`, matches instance and nonce, then
transfers a `MessageChannel` port. An opaque-origin iframe cannot provide a
verifiable origin, so the handshake nonce and single-load rule are the controls.
Check a second `ready`, an extra port, a missing nonce, a message handled before
the handshake, and a page that can reopen or navigate the iframe.

**Plugin page protocol.** The host channel caps pending requests (64), JSON
size (256 KiB), and time (30 s), rejects duplicate in-flight ids, and aborts on
protocol error. The page SDK is frozen and accepts `connect` only from
`window.parent` with matching protocol, version, kind, instance, and nonce.
Check an unvalidated action id, an action not declared on the current page, an
upload that bypasses size/name/type checks, a file ticket used outside
`/api/plugin-files/v1/`, and a response larger than the cap.

**Sandbox escape.** The extension iframe is `sandbox="allow-scripts"` with no
same-origin, forms, or popups; the shell CSP has `default-src 'none'`,
`connect-src 'none'`, `worker-src 'none'`, and `frame-ancestors 'self'`. A page
that reaches the parent origin, Dashboard storage, the network, or a Dashboard
credential is a high-severity finding. An intentional Action through the host
bridge is not.

**Credentialed CORS trust.** The only CORS emission is the plugin page asset
path, which echoes a same-origin or `null` origin for opaque sandbox fetches.
There is no global CORS middleware. Report only an actual reflected/allowed
origin that returns sensitive data or permits a cross-origin mutation.

**Clickjacking and navigation.** The main SPA shell has no CSP or
`frame-ancestors`; missing framing protection is hardening unless a sensitive
action can complete inside the frame. Client navigation must enforce scheme and
destination policy; a `javascript:` or `data:` target from attacker input is a
candidate. Reverse tabnabbing applies only where code keeps `window.opener`.

## Storage and session classes

**Token storage and exfiltration.** The Dashboard JWT is in `localStorage`;
`api/http.ts` attaches it only to same-origin URLs, and a 401 purges it. Any
XSS in the Dashboard can read it. Local storage of the token is not a finding by
itself; require script execution, an extension page escape, a same-origin
less-trusted component, or a cross-origin leak. Drafts, provider/model
bindings, preview settings, and plugin preferences share the same jar.

**Stale authorization.** Logout clears the cookie and local token but the JWT is
stateless; a revoked account is caught by principal re-validation. A cached
response, open socket, or worker that continues after logout or account switch
is a candidate only with a security-relevant effect. The upgrade-recovery JWT in
`sessionStorage` is a second copy; check its lifetime and purge.

**Service workers and caches.** The Dashboard does not register a service
worker. If one appears, check registration scope, update imports, integrity, and
whether it caches personalized responses without account or authorization state.

**XS-Leaks and window state.** An attacker page can distinguish protected
cross-origin state through load/error, frame state, redirect, timing, cache, or
size while the browser attaches victim credentials. Require one concrete
secret-bearing predicate, not generic variance.

## Universal moves

- Start from DOM, navigation, worker, message, and storage sinks, then trace
  backward to browser-only and server-controlled sources. Record the browser
  policy that should stop the path.
- Test account switch, logout, iframe reload, offline fallback, and stale-tab
  state with a local origin and dummy accounts. Never use production users.
- For XS-Leaks, list only predicates proved by source and local browser
  behavior, then identify the header or rendering change that removes the
  oracle.

## Validation rules

1. Cite the source, sink, browser policy, affected origin/session, and
   observable mutation or disclosure.
2. For prototype pollution, prove the recursive write and a security-relevant
   gadget. For DOM clobbering, prove the markup survives and the shadowed value
   is used.
3. For extension pages, prove the handshake or sandbox control is missing and a
   privileged host action or credential is reachable. A protocol error is not
   an escape.
4. For messaging, CORS, WebSocket, and XS-Leak claims, show the exact validation
   and the protected state exposed; confirm CSP, COOP/CORP, cookies, and
   SameSite do not already block it.
5. For storage claims, prove a realistic reader with less authority or a
   continued use after revocation/logout. Token storage alone is hardening.
6. Return `needs_validation` with the precise deployed header, extension
   permission, browser version, or renderer behavior an owner must verify.
