# Prompts

A Prompt controls the system prompt, opening dialogue, tools, Skills, and error reply used by an Agent session. Create Prompts from **Prompts** in the WebUI sidebar and organize larger collections with folders.

## Prompt fields

- **Prompt ID** is the unique identifier referenced by conversations, profiles, SubAgents, and scheduled jobs. Keep it stable after creation.
- **System prompt** defines the role, goals, boundaries, and response style. Do not store secrets or anything that must not be sent to the model.
- **Custom error reply** is sent first when an LLM request using this Prompt fails. Leave it empty to use the system default error message.
- **Opening dialogue** contains alternating user and assistant few-shot examples and must have an even number of entries. These examples enter model context but are not written back as real conversation history.
- **Tools / MCP tools**: `null` means all currently available tools, an explicit name list allows only those tools, and an empty list means no ordinary tools. An empty list still keeps `read_skill` so the Agent can read manuals for Skills enabled on this request.
- **Skills** use the same all, selected-only, or none semantics. An empty Skills list also disables workspace Skills.

Tools and Skills are permission boundaries, not just prompt optimization. Apply least privilege to shell, file-write, browser, external-account, and administrative tools, and review the selection after models or plugins change.

## Which Prompt is selected

The local Agent Runner resolves a Prompt in this order:

1. a forced Prompt configured for the message session under **Session Management**;
2. the Prompt selected on the current conversation record;
3. the profile default Prompt: `agent_runner.config.prompt_id` for both local and third-party runners.

Session rules are useful for pinning a role to a platform, group, or user. Without a forced rule, WebChat can select a Prompt per conversation. Explicitly selecting no Prompt prevents the profile default from being applied.

Updating a Prompt refreshes the runtime cache immediately, so an AstrBot restart is normally unnecessary. Existing history is not rewritten; subsequent model requests use the new definition.

## Conversation commands

Admins can use `/prompt status` to inspect the current selection, `/prompt list` to list Prompts, `/prompt show <prompt_id>` to inspect one, `/prompt set <prompt_id>` to switch the current conversation, and `/prompt unset` to explicitly disable Prompts. Entering `/prompt` alone displays the subcommand tree.

## Folders and deletion

Folders affect WebUI organization and ordering only. They do not change runtime permissions or scope. Deleting a folder moves its Prompts to the root instead of deleting them.

Deleting a Prompt removes its definition but does not rewrite every external reference. Before deletion, check:

- the default Prompt in each profile;
- Session Management rules and existing conversation selections;
- SubAgents, Cron jobs, or plugins that store the Prompt ID.

## Import and export

The Prompt card menu exports JSON, and the page toolbar imports JSON. The current interchange format contains only:

```json
{
  "prompt_id": "researcher",
  "system_prompt": "You are a careful research assistant.",
  "begin_dialogs": ["Summarize this source.", "Please provide the source."]
}
```

The export does **not** include tools, Skills, the custom error reply, folder placement, ordering, or long-term memory.

During import:

- `system_prompt` must be a non-empty string;
- only string entries from `begin_dialogs` are retained;
- the Prompt is placed in the folder currently open in the UI;
- ID conflicts receive `_imported`, `_imported_2`, and similar suffixes;
- tools and Skills are set to “all available.”

> [!WARNING]
> Prompt JSON is prompt input. Review third-party files before importing them, then immediately configure tools and Skills; otherwise the imported Prompt inherits every currently available capability. The export is not a complete backup.

Use AstrBot [runtime-data backup](../deploy/astrbot/backup) for a complete migration instead of relying on Prompt JSON alone. After restoration, verify that referenced plugins, MCP servers, Skills, and Providers still exist because a Prompt stores their names rather than their implementations.

## Related features

- [SubAgent orchestration](./subagent): a SubAgent can bind a Prompt and inherit its prompt, opening dialogue, and tools. Isolated Prompt Skills are not currently inherited.
- [Skills](./skills): a Prompt can narrow the Skill set visible in a session.
- [Long-term memory](./long-term-memory): memory is stored by user and message session, is not included in Prompt exports, and is not automatically erased when a Prompt is deleted.
