---
outline: deep
---

# Function calling

Function calling lets the model invoke external tools in the same turn: web search, reminders, knowledge-base retrieval, sandbox tools, or plugin tools.

Open **Plugins → Manage behavior → Function tools**. MCP and Skills are adjacent tabs. See [MCP](./mcp) and [Skills](./skills).

## Tools versus commands

|                    | Tool                                           | Command                                                                                                  |
| ------------------ | ---------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Who triggers it    | The model picks from a schema                  | The user types a `command_prefixes` command                                                              |
| Where to manage it | **Plugins → Manage behavior → Function tools** | **Command management**                                                                                   |
| Stable ID          | Tool name (plugin and MCP tools add prefixes)  | `command_id`, `{plugin}:{original path}` with spaces as dots, for example `builtin_commands:plugin.list` |

`command_id` is only for enabling, renaming, and permission overrides on **commands**. It is **not** a tool switch. Do not look for `command_id` on the tool panel. See [Built-in commands](./command) and [WebUI command management](./webui#command-management).

## Enable or disable tools

On the tool panel you can:

1. Toggle the master tool switch;
2. Allow or deny built-in, plugin, and MCP tools one by one;
3. Enable native parallel execution (off by default).

The final call still passes three gates: user authorization ∩ tools allowed by the Persona ∩ the tool's own policy. An empty tool list on a Persona means that role cannot use tools. See [Personas](./persona). A sub-agent handoff cannot raise the caller's authority.

High-risk tools (local shell, file write, browser, Computer Use, writable MCP) also need [Authorization](./authorization) and ChatUI step-up. IM messages do not inherit Dashboard `root`.

## Which models work

The following are common examples, not a guarantee for every model, endpoint, or Provider configuration. Mainstream chat models released after 2025 usually support function calling: GPT-5.x, Gemini 3.x, Claude 4.x, DeepSeek v3.2 (`deepseek-chat`), Qwen 3.x. Older DeepSeek-R1 and Gemini 2.0 thinking variants often do not. Confirm with the Provider capability test and the service documentation.

If the server returns `tool call is not supported`, `function calling is not supported`, or `tool use is not supported`, AstrBot usually strips tools and retries. You can also disable every tool on the panel, or switch to a model that supports tools. The Provider "tool calling" switch must match the service. See [Provider configuration](/en/providers/llm).

Plugins may expose tools in addition to commands. Whether a marketplace plugin actually ships tools is up to that plugin's own docs.

Example calls:

![Function-calling example](https://files.astrbot.app/docs/source/images/function-calling/image.png)

![Tool result example](https://files.astrbot.app/docs/source/images/function-calling/image-1.png)

## Native parallel tool execution

Independent calls from the same model turn can run in parallel. The feature is off by default. Turn on the master switch, then allow tools one by one.

These tools cannot be parallel: side effects, direct user delivery, handoffs, background tasks, or an explicit serial policy.

Results are written back in call order even when execution finishes out of order. MCP tools use a per-server concurrency limit (default 1). Allowing a tool to run in parallel does not make a stateful MCP server concurrent.

## Agentic knowledge-base retrieval

When the profile sets `kb_agentic_mode`, retrieval becomes the `astr_kb_search` tool and the model decides when to query. When it is off (default), results are injected into the current request. See [Knowledge base](./knowledge-base#agentic-retrieval).

## Common misconfigurations

1. Looking for tool switches under **Command management**.
2. Leaving many tools on for a model that cannot call functions.
3. The Persona tool list is empty, while the panel looks enabled.
4. Parallel is on, but the MCP server stays serial because per-server concurrency defaults to 1.
