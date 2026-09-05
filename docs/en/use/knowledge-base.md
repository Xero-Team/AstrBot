# Knowledge base

A knowledge base chunks documents, stores vectors, and retrieves related passages during chat. This fork documents only the current workflow. Legacy paths are unsupported.

Open **Knowledge Base**. Profile binding is **Config → AI → Knowledge Base**.

![Knowledge base preview](https://files.astrbot.app/docs/en/use/image-3.png)

## Prepare models

1. Open **Providers** and add an **Embedding** source. Built-in types include OpenAI-compatible, Gemini, NVIDIA NIM, and Ollama.
2. Optionally add a **Rerank** source. Built-in types include vLLM-compatible, Xinference, Bailian, and NVIDIA.
3. Save, then open **Knowledge Base**, create a base, and pick the embedding model (rerank is optional).

After you choose an embedding model, do not change that provider's **model name** or **vector dimension**. Existing FAISS indexes are not migrated. Recall will fail or error. If built-in NVIDIA defaults change, saved Provider rows and existing indexes are not migrated either.

## Upload and chunking

Upload after create. Select many files, or drop a whole folder (for example a Markdown tree). Nested directories are collected recursively. There is no 10-file batch cap. Each file may be up to 128 MB.

![Upload files](https://files.astrbot.app/docs/en/use/image-4.png)

Uploads can override chunk settings. Knowledge-base settings also store defaults:

| Field           | Default | Role                                 |
| --------------- | ------- | ------------------------------------ |
| `chunk_size`    | `512`   | Approximate characters per chunk     |
| `chunk_overlap` | `50`    | Overlap so sentences are not cut off |

Markdown is split on headings. Changing chunk size does not rewrite documents already stored; re-upload them.

An upload writes the document store, metadata, and local vectors together. Any step that fails runs compensating cleanup: after the API reports failure, that document must not stay queryable. Storage is SQLite in the runtime directory plus FAISS indexes under `data/knowledge_base/`. It is a single-process, single-node deployment. Runtime startup enforces that with `data/astrbot.lock`; on POSIX it also locks the `data/` directory, so deleting the lock file cannot bypass the singleton. SQLite WAL and `busy_timeout` are not an instance lock. The operating system releases this advisory lock when the process exits, and a leftover lock file does not mean an instance is still running. If Compose mounts the same `./data` into a second full instance, the later container is expected to fail.

## Attach to a session

Chat does not search every knowledge base you created. You must name them on the profile or a rule.

### Profile

**Config → Knowledge Base**:

| Field             | Default | Notes                                                       |
| ----------------- | ------- | ----------------------------------------------------------- |
| `kb_names`        | Empty   | Default knowledge-base names for this profile. Multi-select |
| `kb_fusion_top_k` | `20`    | Rows kept after multi-base fusion                           |
| `kb_final_top_k`  | `5`     | Rows injected or returned                                   |
| `kb_agentic_mode` | Off     | Next section                                                |

Empty `kb_names` means this profile does not retrieve. Different profiles can bind different lists. See [Configuration profiles](./config-profiles).

### Custom rules

`kb_config.kb_ids` on a rule overrides the profile list. An empty list means **this session uses no knowledge base**. You can also set `top_k`. See [Custom rules](./custom-rules).

The **Retrieval** tab on the knowledge-base page can test recall without sending a group message.

## Agentic retrieval

Default (`kb_agentic_mode = false`): every LLM request retrieves against the user text and injects hits as temporary context.

When Agentic is on: retrieval becomes the `astr_kb_search` tool and the model decides when to call it. The model must support function calling, and the tool panel must not disable that tool. See [Function calling](./function-calling).

Use Agentic when some turns need documents and some are small talk. Use default injection when almost every turn on this profile should ground in the corpus.

## Common misconfigurations

1. The knowledge base exists, but profile `kb_names` is still empty.
2. You changed the embedding model or dimension and kept the old index.
3. A custom rule `kb_ids` points at a deleted base, so retrieval looks dead.
4. Agentic is on, but the model cannot call tools or the Persona forbids the tool.
5. A failed upload is still searchable — treat that as a defect, clean up, and re-upload.

If this happens, do not upload the same file again immediately:

1. Open the knowledge-base document list and delete the residual document;
2. Check the AstrBot startup log and errors around the upload time;
3. Use the **Retrieval** tab to confirm that the residual content is gone;
4. Upload the file again. If deletion fails or the index is inconsistent, back up `data/knowledge_base/` and the runtime directory, stop AstrBot, and contact the maintainer. Do not edit FAISS files by hand.
