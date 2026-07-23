"""Contracts shared by platform-specific Dashboard provisioning flows."""

from __future__ import annotations

import secrets
import string
from typing import Any, Protocol


class PlatformProvisioner(Protocol):
    """Create or poll credentials for one platform adapter type."""

    async def __call__(
        self,
        *,
        action: str,
        payload: dict[str, Any],
        platform_config: dict[str, Any],
    ) -> dict[str, Any]: ...


class PlatformProvisioningValidationError(ValueError):
    """Raised when a provisioning action payload is invalid for an adapter."""


def random_platform_id_suffix() -> str:
    """Return the collision-resistant suffix used for generated platform IDs."""

    return "_" + "".join(secrets.choice(string.ascii_lowercase) for _ in range(4))
