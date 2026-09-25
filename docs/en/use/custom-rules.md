# Custom rules

Custom rules override a configuration profile for one unified message origin (UMO) or one sender. Use them for a few exceptions. Do not split a whole profile just to change one group's prompt or turn TTS off.

A UMO uniquely identifies one session on one platform. Sender overlays use the full subject ID `im:{platform instance}:{bot account}:{sender id}`. `/session info` prints both. Profiles themselves are in [Configuration profiles](./config-profiles).

Open **Custom rules**. Choose **Session** or **Sender** at the top of the page. The page help icon points here.

## When to use a rule versus a profile

| Need                                                                     | Use                                           |
| ------------------------------------------------------------------------ | --------------------------------------------- |
| One model, wake policy, and plugin set for a platform or class of groups | Create or bind a [profile](./config-profiles) |
| Disable LLM, pin a prompt, or change knowledge bases for one group       | Custom rule (session)                         |
| Block one person in a shared group, or enable LLM for one person         | Custom rule (sender) or `/user`               |
| Temporarily silence the current session                                  | `/bot disable` or session on/off on this page |

Rules outrank the profile. If a rule disables LLM, enabling it on the profile does nothing. With no rule, IM groups and direct messages default session, LLM, and TTS off. Dashboard WebChat still defaults on.

## Rule types

Session rules bind to one UMO and may include several overlays. Sender rules bind to an `im:` subject ID and only store `blocked` / `llm_enabled` on the service overlay.

### Service rules (`session_service_config`)

- Whether to process messages for this session. Off is equivalent to blacklisting the UMO.
- Whether LLM is enabled. Off skips AI; commands may still run.
- Whether TTS is enabled.
- Whether all functionality is fully blocked (`session_blocked`). A fully blocked session only allows `/bot status` and `/session unblock`.
- Forced prompt. Outranks conversation choice and the profile default. See [Prompts](./prompt#which-prompt-is-selected).
- Display alias. This is the same `user_alias` written by `/session name`, not a separate `custom_name` field.

`/bot enable`, `/bot disable`, `/tts enable`, `/tts disable`, `/session block`, and `/session unblock` still write this service rule against the UMO. IM `/llm enable` and `/llm disable` write the canonical session key, so they disable LLM for the whole group when isolated sessions are on. Dashboard custom rules still save prompt and TTS against the UMO, and dual-write `llm_enabled` / `session_enabled` / `session_blocked` onto the canonical session key. `/bot status` shows the session, LLM, TTS, and full-block switches. Those commands need `session.manage` or `session.block`. See [Built-in commands](./command).

When `unlisted_sessions=deny`, the admission stage looks at overlays on the canonical session key. IM `/llm` and Dashboard rules on this page both list that key. Session on/off and full block still belong to the later session-status stage, which still reads the UMO.

### Sender overlays (sender)

Sender overlays live on `scope=sender` with `scope_id=Subject.im.id` (`im:{platform instance}:{bot account}:{sender id}`). Only `blocked` and `llm_enabled` are honored. They apply to every session on this bot instance, including shared groups with isolated sessions off; they are not a `UMO×UID` selector. Prompt, TTS, knowledge bases, providers, and plugin disables still belong to session rules.

The **Sender** target on this page and `/user block`, `/user unblock`, and `/user llm on|off` read and write the same preference row. Dashboard requires the full `im:` subject ID; chat `/user` can also mint a raw sender id from the current session. See [Built-in commands](./command). Save applies immediately; a restart is unnecessary. Deleting the row unlists that sender.

An unwritten `llm_enabled` follows the session. The Dashboard sender editor offers follow session, enabled, and disabled, stores only what you set, and leaves `blocked` unwritten unless you check it, so saving an untouched rule does not change admission. Returning a written value to follow session removes the field; deleting the rule removes the whole row.

### Plugin rules (`session_plugin_config`)

Disable selected plugins for this UMO. Plugins not listed remain enabled. When all three layers exist:

1. A global disable on the plugin page: checking the plugin here still will not load it.
2. Profile `plugin_set`: limits plugins for that profile.
3. This rule: disables plugins for the session.

See [Plugins](./plugin).

### Knowledge-base rules (`kb_config`)

- `kb_ids` overrides the profile `knowledge_base.names`. An empty list means this session uses no knowledge base.
- `top_k` and rerank apply only to this session.

See [Knowledge base](./knowledge-base#attach-to-a-session).

### Provider overrides

Pin chat, STT, or TTS models for this UMO. Unset fields follow the profile. Speech master switches still follow the service rule and the profile. See [Speech STT / TTS](./speech).

## Steps

1. Open **Custom rules**, choose **Session** or **Sender**, and add a rule.
2. Session: pick a UMO that has already appeared, or fill platform / type / session. Sender: paste a full `im:` subject ID.
3. Change only the fields you need to override. Sender rows only have block and LLM.
4. Save. It applies immediately; a restart is usually unnecessary.
5. Delete the rule to fall back to the profile or unlisted behavior.

The session view supports UMO search, bulk delete, and grouping. The sender view supports subject-ID search and delete; it has no groups or batch provider updates.

## Common misconfigurations

1. A rule disabled the session or LLM, so the group looks dead while `llm_access` looks correct. Check `/bot status`.
2. The rule pins a prompt, then you edit the profile default and expect this group to follow.
3. `kb_ids` points at a deleted knowledge base, so retrieval is skipped.
4. You created a profile per group and left the rule table empty.
5. You tried to block one person with a session rule or the old allowlist. Per-person refusal is a sender overlay; do not paste an `im:` ID into a UMO field.
