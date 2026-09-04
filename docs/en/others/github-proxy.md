# GitHub mirrors

This fork **does not ship** a default GitHub mirror list, and Dashboard no longer accepts arbitrary custom mirror input.

Plugin install and plugin update only request:

- Official GitHub-related hosts;
- The plugin marketplace, which first requests the upstream `cloud.astrbot.app` market JSON and on failure requests the GitHub collection `AstrBotDevs/AstrBot_Plugins_Collection` and the jsDelivr CDN. These are upstream services, not a market operated by this fork. The default market has no MD5 check and is refetched every time it is opened; only a custom market uses the matching `-md5.json`. JSON requests use `http_proxy` from config and do not read process environment proxies.
- Public HTTPS origins that pass backend validation.

If an API call includes a mirror prefix, it must be:

- An explicit HTTPS origin;
- Without a username or password;
- Resolved entirely to public addresses;
- Unable to redirect to an unchecked internal address.

This is not a normal HTTP forward proxy. The semantics are a URL-prefix mirror, and every hop is re-validated. A plugin `download_url` still rejects private networks and non-HTTPS even when the caller is a logged-in installer.
