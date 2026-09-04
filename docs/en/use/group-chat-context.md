# Group Chat Context Awareness

Group chat context awareness records group messages after the bot's last reply and injects them as extra context on the next LLM wake. It applies to group chats only and is off by default. It does not decide whether a message wakes the bot. Wake policy is in [When the bot replies in groups](./group-wake).

The settings live under **Config → Ext. → Group Chat Context Awareness**. The JSON key is still the historical name `provider_ltm_settings`. Do not treat it as the switch for Alkaid [Long-term Memory](./long-term-memory).

## What is recorded

When `group_icl_enable` is on, AstrBot keeps group messages in memory per unified message origin (UMO) until the next LLM request:

- text, mentions, quotes, forwarded-message summaries, and JSON card summaries;
- optional group-chat image captions, configured separately from captions on the current main-agent request;
- command messages are not recorded.

After injection, records already sent to the model are dropped; only later messages remain. `/conversation reset` clears the in-memory cache for that session.

`group_message_max_cnt` caps the in-memory buffer, default `300`. Restarting AstrBot discards uninjected memory records.

## Persisted group message history

`group_message_history_enable` is a separate path: it writes group messages to the database for the `get_group_message_history` tool. It does not replace the in-memory injection above. It is off by default. `group_message_history_max_cnt` controls retention, default `700`.

## Group-chat image captions

`image_caption` only describes images in group-chat context and requires its own `image_caption_provider_id`. Captions for the current main-agent request and quoted images still use `provider_settings.default_image_caption_provider_id`.

- `image_caption_scope`: `all` / `allowlist` / `denylist`
- `image_caption_groups`: full UMOs only
- `image_caption_min_interval` and `image_caption_max_concurrency`: rate limits
- `image_caption_cache_ttl`: default `0` (off)
- `image_caption_lazy`: store a placeholder first and caption only when the LLM actually wakes

## Difference from long-term memory

|        | Group chat context awareness                             | Alkaid long-term memory                          |
| ------ | -------------------------------------------------------- | ------------------------------------------------ |
| Role   | Inject recent group messages into the next LLM request   | Extract facts, profiles, and episodes from chats |
| Scope  | Current group session (UMO)                              | User and message session                         |
| Switch | `provider_ltm_settings.group_icl_enable`, off by default | No profile-level enable switch today             |
