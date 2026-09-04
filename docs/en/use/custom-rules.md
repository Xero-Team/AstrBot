# Custom rules

Custom rules override a configuration profile for one unified message origin (UMO). Use them for a few exceptions. Do not split a whole profile just to change one group's persona or turn TTS off.

A UMO uniquely identifies one session on one platform. `/session info` prints it. Profiles themselves are in [Configuration profiles](./config-profiles).

Open **Custom rules**. The page help icon points here.

## When to use a rule versus a profile

| Need                                                                     | Use                                           |
| ------------------------------------------------------------------------ | --------------------------------------------- |
| One model, wake policy, and plugin set for a platform or class of groups | Create or bind a [profile](./config-profiles) |
| Disable LLM, pin a persona, or change knowledge bases for one group      | Custom rule                                   |
| Temporarily silence the current session                                  | `/bot disable` or session on/off on this page |

Rules outrank the profile. If a rule disables LLM, enabling it on the profile does nothing. With no rule, the session defaults to everything enabled (legacy compatibility).

## Rule types

Each rule binds to one UMO and may include several overlays:

### Service rules (`session_service_config`)

- Whether to process messages for this session. Off is equivalent to blacklisting the UMO.
- Whether LLM is enabled. Off skips AI; commands may still run.
- Whether TTS is enabled.
- Forced persona. Outranks conversation choice and the profile default. See [Personas](./persona#which-persona-is-selected).
- Display name (`custom_name`).

`/bot enable`, `/bot disable`, `/llm enable`, and `/llm disable` write this same service rule. `/bot status` shows the session, LLM, and TTS switches. Those commands need `session.manage`. See [Built-in commands](./command).

### Plugin rules (`session_plugin_config`)

Disable selected plugins for this UMO. Plugins not listed remain enabled. When all three layers exist:

1. A global disable on the plugin page: checking the plugin here still will not load it.
2. Profile `plugin_set`: limits plugins for that profile.
3. This rule: disables plugins for the session.

See [Plugins](./plugin).

### Knowledge-base rules (`kb_config`)

- `kb_ids` overrides the profile `kb_names`. An empty list means this session uses no knowledge base.
- `top_k` and rerank apply only to this session.

See [Knowledge base](./knowledge-base#attach-to-a-session).

### Provider overrides

Pin chat, STT, or TTS models for this UMO. Unset fields follow the profile. Speech master switches still follow the service rule and the profile. See [Speech STT / TTS](./speech).

## Steps

1. Open **Custom rules** and add a rule.
2. Pick a UMO that has already appeared, or fill platform / type / session.
3. Change only the fields you need to override.
4. Save. It applies immediately; a restart is usually unnecessary.
5. Delete the rule to fall back to the profile.

The page supports UMO search, bulk delete, and grouping.

## Common misconfigurations

1. A rule disabled the session or LLM, so the group looks dead while `llm_access` looks correct. Check `/bot status`.
2. The rule pins a persona, then you edit the profile default and expect this group to follow.
3. `kb_ids` points at a deleted knowledge base, so retrieval is skipped.
4. You created a profile per group and left the rule table empty.
