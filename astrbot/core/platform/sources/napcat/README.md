# NapCat Adapter

This directory contains AstrBot's standalone `napcat` platform adapter.

It is intentionally split into generated code and handwritten runtime glue.

## Layout

- `generated/ob11_events.py`
  Generated Pydantic models for NapCat `OB11AllEvent`.
- `forward_ws_client.py`
  Handwritten forward WebSocket transport client for NapCat OneBot v11.
- `napcat_platform_adapter.py`
  Handwritten AstrBot platform adapter implementation.
- `message_event.py`
  Handwritten AstrBot event wrapper with NapCat-specific helpers.
- `types.py`
  Small handwritten normalized result types used by the runtime layer.
- `exceptions.py`
  Handwritten error types used by the adapter and transport client.

## Do Not Edit

Do not manually edit anything under `generated/`.

Those files are replaced by code generation and should be treated as build artifacts.

## Regenerate

From the repository root:

```bash
make napcat-codegen
```

This will:

1. Generate JSON Schema for `OB11AllEvent`.
2. Normalize the schema and regenerate `generated/ob11_events.py`.
## Validate

From the repository root:

```bash
make napcat-test
make napcat-check
```

- `make napcat-test` runs the NapCat-focused unit suite only.
- `make napcat-check` runs code generation and the NapCat-focused unit suite.

## Common Changes

- Add or adjust a WebSocket transport helper:
  Edit `forward_ws_client.py`, then add focused transport tests.
- Add or adjust an AstrBot-facing event helper:
  Edit `message_event.py`, then add tests in `tests/unit/test_napcat_adapter.py`.
- Add or adjust message conversion:
  Edit `napcat_platform_adapter.py`, then add adapter tests.
- Refresh NapCat upstream models:
  Run `make napcat-codegen`, then rerun `make napcat-check`.

## Rule Of Thumb

If a change is about AstrBot semantics, error handling, normalization, or platform actions, it belongs in handwritten files.

If a change is about upstream NapCat schemas, regenerate instead of patching generated files.
