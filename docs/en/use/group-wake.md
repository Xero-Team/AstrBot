# When the bot replies in groups

If the bot ignores a group message, the model is usually fine. The active configuration profile's LLM access policy did not admit that message.

This page only covers **whether a message is sent to the AI**. Injecting recent group messages into the next request is [Group Chat Context Awareness](./group-chat-context).

Open **Config → Platform → General**. These fields belong to the current profile. Editing `default` does not change a group bound to another profile. See [Configuration profiles](./config-profiles).

## Defaults

| Scene          | Default                           | Effect                                 |
| -------------- | --------------------------------- | -------------------------------------- |
| Direct message | `llm_access.private = open`       | Ordinary text goes to the LLM          |
| Group          | `llm_access.group = prefix`       | Requires an LLM prefix                 |
| LLM prefix     | `llm_access.prefixes = ["/"]`     | `/hello` is handled; `hello` is not    |
| Reply to bot   | `llm_access.reply_to_bot = false` | Replying does not extra-admit the turn |

After a default install: talk freely in DMs. In a group, `/hello` starts a chat and `hello` does not.

## Command prefixes and LLM prefixes are separate

| Field                 | Dashboard label      | Role                                                                  |
| --------------------- | -------------------- | --------------------------------------------------------------------- |
| `command_prefixes`    | Command prefixes     | Frames command headers only. Default `["/"]`                          |
| `llm_access.prefixes` | LLM trigger prefixes | Complete strings users type. Never concatenated with command prefixes |

Routing **always matches commands before LLM access**:

1. An enabled command runs as a command. The model is not called.
2. A bare command group (for example `/plugin`) shows subcommand help.
3. An unknown subcommand returns an Orbit diagnostic and is **not** treated as an LLM prompt.
4. Everything else follows `llm_access`.

Both prefix lists default to `/`. A non-empty LLM prefix occupies that profile's first command root. Dashboard rejects a save that conflicts with an enabled command. See [Built-in commands](./command).

## Group policy

`llm_access.group` values:

| Value               | When the LLM runs                           |
| ------------------- | ------------------------------------------- |
| `open`              | Every ordinary group message. Easy to flood |
| `prefix`            | Default. Message starts with an LLM prefix  |
| `mention`           | @ the bot, or @ everyone (see exceptions)   |
| `prefix_or_mention` | Prefix **or** mention                       |
| `off`               | Do not open a new LLM turn                  |

Two extra conditions:

- **Allow LLM when replying to the bot** (`reply_to_bot`): an additional OR. Even `group=off` can wake on a reply to the bot.
- **@ everyone**: if the group policy is not `off` and `ignore_at_all` is off, @ everyone admits the LLM. `ignore_at_all` lives under **Platform → Other**.

A message that starts by @-ing **someone else** does not wake on prefix. That keeps talk directed at other people from hitting the bot.

### Suggested recipes

- Large group, low noise: keep `prefix`.
- Only answer mentions: set `mention`.
- Also answer replies: turn on `reply_to_bot`.
- Anyone may chat: set `open` (this raises call volume).

`llm_access.private` is only `open` / `prefix` / `off`. `off` blocks new LLM turns; an in-flight continuation may still continue.

## Continuations

If the session already has an open LLM turn window (inbound coalesce waiting for the rest of a sentence, or a turn still running), later fragments can continue without repeating the prefix. A real command discards the buffered turn. Inbound coalesce is off by default and currently merges **direct messages only**. See [Platform handling](./platform-settings#inbound-turn-coalescing).

Some adapters stamp a preconfigured wake flag and bypass the group `llm_access` gate. Do not use that as a substitute for the policy above.

## Mention-only messages

**Platform → General → Wait after a mention-only message** (`empty_mention_waiting`) is on by default. A message that is only @-bot waits up to 60 seconds for that user's next message. This is not `llm_access` and is not a complete turn by itself.

## Isolated sessions

**Isolated sessions** (`platform_settings.unique_session`) is off by default: one group shares one conversation. When on, each member gets a separate context.

- Mutually exclusive with experimental group-sender concurrency.
- Group notice/request events stay on the group session.
- `/session info` also reports the group ID used for allowlists when isolation is on.

Isolation changes **who owns the context**. It does not relax `llm_access.group`.

## Still dropped after a wake

Pipeline order: wake check → [allowlist](./platform-settings#allowlist) → session enabled → coalesce → rate limit → content safety → preprocess → plugin or LLM.

A policy admit can still vanish behind an allowlist, a custom rule that disabled the session, rate limits, or content safety. Session on/off is in [Custom rules](./custom-rules).

## Common misconfigurations

1. Talking plainly in a group while `group` is still the default `prefix`.
2. Changing `command_prefixes` and expecting the LLM prefix to follow.
3. Editing `default` while the group is bound to another profile. Check the UMO with `/session info`.
4. Setting `mention` on a platform that does not parse @ into an At segment.
5. Assuming a reply equals a mention; `reply_to_bot` is a separate switch.
6. Allowlist enabled with a non-empty list that omits this group.
7. A custom rule or `/llm disable` turned LLM off for the session.
