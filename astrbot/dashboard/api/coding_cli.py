"""Manage the provider presets a coding CLI's own configuration is switched between.

The run path layers a config the CLI loads in addition to the user's own, so a
delegated run never rewrites what the operator runs interactively.  These routes
are the other, explicitly-invoked path: the operator asking for one provider to
become the CLI's default on this host.  That replaces the user's own settings
and persists a credential in a file AstrBot does not own, so a switch is
high-risk and therefore step-up.

The provider list itself is ordinary configuration (``btw.cli_providers``), and
is saved through the config profile the same way any other setting is.  Only
the switch touches a file outside AstrBot's data directory.
"""

from typing import Any, NoReturn

from fastapi import APIRouter, Depends, Request

from astrbot.core.agent.btw import cli_global_config
from astrbot.core.auth.models import Resource
from astrbot.dashboard.responses import ApiError, ok
from astrbot.dashboard.schemas import CodingCliSwitchRequest

from .auth import (
    AuthContext,
    require_resource_action,
    require_scope,
)

router = APIRouter(tags=["Coding CLI"])

# Every write into a CLI's own global config asks for this one action.
WRITE_ACTION = "coding_cli.config.write"


async def require_coding_cli_scope(request: Request) -> AuthContext:
    """Authenticate as config management; the action is decided per resource."""
    return await require_scope(request, "config", authorize_action=False)


async def authorize_coding_cli(request: Request, auth: AuthContext) -> None:
    """Require the high-risk action that switching a CLI's provider needs."""
    await require_resource_action(
        request,
        auth,
        action=WRITE_ACTION,
        resource=Resource.instance("default"),
    )


def _raise(exc: Exception) -> NoReturn:
    raise ApiError(str(exc), status_code=400) from exc


def _state(cli: str) -> dict[str, Any]:
    """Serialize one CLI's state without ever naming a stored credential."""
    state = cli_global_config.read_state(cli)
    return {
        "cli": cli,
        "path": str(state.path),
        "exists": state.exists,
        "managed": state.managed,
        "backed_up": state.backed_up,
        "base_url": state.base_url,
        "model": state.model,
        "has_credential": state.has_credential,
    }


def _is_current(provider: dict, state: cli_global_config.ManagedFile) -> bool:
    """Return whether the CLI's file currently holds this provider.

    Compares the endpoint and model rather than the credential: AstrBot cannot
    read a stored key back, and the endpoint is what identifies a provider.
    """
    if not state.managed or not provider["base_url"]:
        return False
    if provider["base_url"] != state.base_url:
        return False
    return not provider["model"] or provider["model"] == state.model


def _cli_payload(cli: str, raw: Any) -> dict[str, Any]:
    """One CLI's file state plus the providers it can be switched to."""
    state = cli_global_config.read_state(cli)
    return {
        **_state(cli),
        "providers": [
            {
                "id": provider["id"],
                "name": provider["name"],
                "base_url": provider["base_url"],
                "model": provider["model"],
                "note": provider["note"],
                # A key is reported as present, never as its value.
                "has_api_key": bool(provider["api_key"]),
                "current": _is_current(provider, state),
            }
            for provider in cli_global_config.providers_for_cli(raw, cli)
        ],
    }


def _provider_for(cli: str, config: Any, provider_id: str) -> dict:
    """Return the named provider from the profile's list, or refuse."""
    btw = config.get("btw", {}) if isinstance(config, dict) else {}
    raw = btw.get("cli_providers") if isinstance(btw, dict) else None
    provider = cli_global_config.select_provider(raw, provider_id)
    if provider is None:
        raise ApiError(f"No provider with the id {provider_id!r} is configured.")
    if provider["cli"] and provider["cli"] != cli:
        raise ApiError(
            f"The provider {provider_id!r} is scoped to {provider['cli']!r}, so it "
            f"cannot be applied to {cli!r}."
        )
    return provider


def _config_of(request: Request) -> Any:
    """Return the running profile, which holds the operator's provider list."""
    runtime = getattr(request.app.state, "runtime", None)
    services = getattr(runtime, "services", None)
    profiles = getattr(services, "config_profiles", None)
    acm = getattr(profiles, "acm", None)
    configs = getattr(acm, "confs", None)
    if not isinstance(configs, dict):
        raise ApiError("Configuration is unavailable", status_code=503)
    return configs.get("default", {})


@router.get("/coding-cli/global-config")
async def get_global_config(
    request: Request,
    auth: AuthContext = Depends(require_coding_cli_scope),
):
    """Report each CLI's own configuration and the providers it can use."""
    await authorize_coding_cli(request, auth)
    btw = _config_of(request).get("btw", {})
    raw = btw.get("cli_providers") if isinstance(btw, dict) else None
    return ok(
        {
            "clis": [
                _cli_payload(cli, raw)
                for cli in cli_global_config.CODING_GLOBAL_AGENT_TYPES
            ]
        }
    )


@router.put("/coding-cli/global-config")
async def switch_provider(
    payload: CodingCliSwitchRequest,
    request: Request,
    auth: AuthContext = Depends(require_coding_cli_scope),
):
    """Make one configured provider the CLI's default on this host."""
    await authorize_coding_cli(request, auth)
    provider = _provider_for(payload.cli, _config_of(request), payload.provider_id)
    try:
        cli_global_config.apply_provider(payload.cli, provider)
    except (OSError, ValueError) as exc:
        _raise(exc)
    return ok(_state(payload.cli))


@router.delete("/coding-cli/global-config/{cli}")
async def remove_global_config(
    cli: str,
    request: Request,
    auth: AuthContext = Depends(require_coding_cli_scope),
):
    """Take AstrBot's configuration back out of the CLI's own file."""
    await authorize_coding_cli(request, auth)
    if cli not in cli_global_config.CODING_GLOBAL_AGENT_TYPES:
        raise ApiError(f"Unknown coding agent type: {cli!r}")
    try:
        cli_global_config.remove_provider(cli)
    except (OSError, ValueError) as exc:
        _raise(exc)
    return ok(_state(cli))
