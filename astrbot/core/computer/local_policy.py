"""Immutable Local computer sandbox policy objects and bounds.

This module is deliberately independent of configuration defaults and platform
launchers so the same resolved policy can be validated once and consumed by the
shell launcher, file tools, and the runtime proxy.
"""

from __future__ import annotations

import ipaddress
import os
import re
import sys
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import Any, Literal

MAX_DOMAIN_RULES = 256
MAX_PATH_RULES = 256
MAX_UNIX_PATHS = 64
MAX_RULE_CHARACTERS = 512
MAX_VALIDATION_ERRORS = 32

_NETWORK_MODES = frozenset({"off", "allowlist", "unrestricted"})
_FILESYSTEM_SCOPES = frozenset({"none", "workspace", "host"})
_UNIX_SOCKET_MODES = frozenset({"deny", "allow_all"})
_PATH_MAGIC = frozenset({"*", "?", "["})
_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")
_HOST_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")

DomainValue = ipaddress.IPv4Address | ipaddress.IPv6Address


@dataclass(frozen=True, slots=True)
class DomainRule:
    """One parsed domain or IP allow/deny rule.

    Args:
        pattern: Canonical hostname, IP literal, or ``*`` wildcard.
        port: Optional destination port; ``None`` matches every port.
        wildcard: Whether the rule matches subdomains of ``pattern``.
        address: Parsed IP literal when the rule names an address.
    """

    pattern: str
    port: int | None = None
    wildcard: bool = False
    address: DomainValue | None = None

    def matches(self, hostname: str, port: int) -> bool:
        """Return whether this rule matches a resolved destination."""
        if self.port is not None and self.port != port:
            return False
        normalized = normalize_hostname(hostname)
        if self.address is not None:
            return normalize_hostname(str(self.address)) == normalized
        if self.pattern == "*":
            return True
        if self.wildcard:
            return normalized.endswith(f".{self.pattern}")
        return normalized == self.pattern


@dataclass(frozen=True, slots=True)
class LocalNetworkPolicy:
    """Network reachability policy for Local execution."""

    mode: Literal["off", "allowlist", "unrestricted"] = "off"
    allowed_domains: tuple[str, ...] = ()
    denied_domains: tuple[str, ...] = ()
    allow_private_network: bool = False
    allow_loopback: bool = False

    @property
    def enabled(self) -> bool:
        """Return whether sandboxed networking is requested."""
        return self.mode != "off"


@dataclass(frozen=True, slots=True)
class LocalFilesystemPolicy:
    """Additional filesystem masks applied on top of the access scope."""

    deny_read: tuple[str, ...] = ()
    deny_write: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalUnixSocketPolicy:
    """Unix-domain socket policy for sandboxed workloads."""

    mode: Literal["deny", "allow_all"] = "deny"
    allowed_paths: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class LocalSandboxPolicy:
    """Complete immutable Local permission policy for one role."""

    allow_execution: bool = False
    filesystem_scope: Literal["none", "workspace", "host"] = "workspace"
    network: LocalNetworkPolicy = LocalNetworkPolicy()
    filesystem: LocalFilesystemPolicy = LocalFilesystemPolicy()
    unix_sockets: LocalUnixSocketPolicy = LocalUnixSocketPolicy()

    @property
    def requires_sandbox(self) -> bool:
        """Return whether this policy needs OS isolation to remain honest.

        Native execution is exactly ``host`` scope, unrestricted network with
        both address flags enabled, no filesystem denies, and all Unix sockets.
        Any deviation requires a real sandbox backend; an unavailable backend
        must fail closed instead of running natively.
        """
        if not self.allow_execution:
            return False
        return bool(
            self.filesystem_scope != "host"
            or self.network.mode != "unrestricted"
            or self.network.denied_domains
            or not self.network.allow_private_network
            or not self.network.allow_loopback
            or self.filesystem.deny_read
            or self.filesystem.deny_write
            or self.unix_sockets.mode != "allow_all"
            or self.unix_sockets.allowed_paths
        )

    @property
    def is_native(self) -> bool:
        """Return whether execution is the unrestricted native combination."""
        return self.allow_execution and not self.requires_sandbox

    def to_dict(self) -> dict[str, Any]:
        """Return the persisted nested configuration shape."""
        return {
            "allow_execution": self.allow_execution,
            "filesystem_scope": self.filesystem_scope,
            "network": {
                "mode": self.network.mode,
                "allowed_domains": list(self.network.allowed_domains),
                "denied_domains": list(self.network.denied_domains),
                "allow_private_network": self.network.allow_private_network,
                "allow_loopback": self.network.allow_loopback,
            },
            "filesystem": {
                "deny_read": list(self.filesystem.deny_read),
                "deny_write": list(self.filesystem.deny_write),
            },
            "unix_sockets": {
                "mode": self.unix_sockets.mode,
                "allowed_paths": list(self.unix_sockets.allowed_paths),
            },
        }

    def without_execution(self) -> LocalSandboxPolicy:
        """Return a blocked copy that keeps displayable configured fields."""
        return replace(self, allow_execution=False)


def default_policy(role: str) -> LocalSandboxPolicy:
    """Return the fresh-install policy for a role.

    Args:
        role: Permission matrix row name.

    Returns:
        Native host execution for administrators and file-only workspace access
        for members. Fresh restricted policies keep both address guards off.
    """
    if role == "admin":
        return LocalSandboxPolicy(
            allow_execution=True,
            filesystem_scope="host",
            network=LocalNetworkPolicy(
                mode="unrestricted",
                allow_private_network=True,
                allow_loopback=True,
            ),
            unix_sockets=LocalUnixSocketPolicy(mode="allow_all"),
        )
    return LocalSandboxPolicy(
        allow_execution=False,
        filesystem_scope="workspace",
        network=LocalNetworkPolicy(mode="off"),
        unix_sockets=LocalUnixSocketPolicy(mode="deny"),
    )


def default_policy_dict(role: str) -> dict[str, Any]:
    """Return a mutable nested default policy document for ``role``."""
    return default_policy(role).to_dict()


def normalize_hostname(hostname: str) -> str:
    """Return the lowercase IDNA form without a trailing dot."""
    value = hostname.strip().rstrip(".").lower()
    if not value:
        return ""
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        pass
    try:
        return value.encode("idna").decode("ascii").lower()
    except UnicodeError:
        return value


def parse_domain_rule(rule: str) -> DomainRule:
    """Parse one canonical domain, IP, wildcard, or optional-port rule.

    Args:
        rule: Raw configured rule.

    Returns:
        Parsed rule suitable for exact comparison.

    Raises:
        ValueError: If the rule is malformed or noncanonical.
    """
    if not isinstance(rule, str):
        raise ValueError("Domain rules must be strings.")
    value = rule.strip()
    if not value:
        raise ValueError("Domain rules must not be empty.")
    if len(value) > MAX_RULE_CHARACTERS:
        raise ValueError(
            f"Domain rules must be at most {MAX_RULE_CHARACTERS} characters."
        )
    if "@" in value:
        raise ValueError("Domain rules must not contain credentials.")

    host = value
    port: int | None = None
    if value.startswith("["):
        closing = value.find("]")
        if closing < 0:
            raise ValueError("Bracketed IPv6 rules require a closing bracket.")
        host = value[1:closing]
        remainder = value[closing + 1 :]
        if remainder:
            if not remainder.startswith(":"):
                raise ValueError("Unexpected text after a bracketed IPv6 address.")
            port = _parse_port(remainder[1:])
        try:
            address = ipaddress.IPv6Address(host)
        except ValueError as exc:
            raise ValueError("Malformed IPv6 address rule.") from exc
        return DomainRule(
            pattern=str(address),
            port=port,
            address=address,
        )

    if value.count(":") == 1:
        host, raw_port = value.rsplit(":", 1)
        port = _parse_port(raw_port)
    elif value.count(":") > 1:
        try:
            address = ipaddress.IPv6Address(value)
        except ValueError as exc:
            raise ValueError("IPv6 rules with a port must use brackets.") from exc
        return DomainRule(pattern=str(address), port=None, address=address)

    if not host:
        raise ValueError("Domain rules must include a hostname.")
    if host == "*":
        return DomainRule(pattern="*", port=port)

    wildcard = host.startswith("*.")
    if "*" in host and not wildcard:
        raise ValueError("Only a leading `*.` wildcard is supported.")
    if wildcard:
        host = host[2:]
        if not host:
            raise ValueError("A wildcard rule requires a domain suffix.")

    if re.fullmatch(r"[0-9.]+", host) and host.count(".") == 3:
        try:
            canonical_ipv4 = str(ipaddress.IPv4Address(host))
        except ValueError as exc:
            raise ValueError("Malformed IPv4 address rule.") from exc
        if canonical_ipv4 != host:
            raise ValueError("IPv4 rules must use canonical notation.")
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        if wildcard:
            raise ValueError("IP literal rules cannot use a wildcard.")
        if str(literal) != host.lower():
            raise ValueError("IP literal rules must use canonical notation.")
        return DomainRule(pattern=str(literal), port=port, address=literal)

    normalized = normalize_hostname(host)
    if not normalized:
        raise ValueError("Malformed domain rule.")
    labels = normalized.split(".")
    if len(normalized) > 253 or any(
        not label or len(label) > 63 or not _HOST_LABEL.fullmatch(label)
        for label in labels
    ):
        raise ValueError("Malformed domain rule.")
    return DomainRule(pattern=normalized, port=port, wildcard=wildcard)


def _parse_port(raw: str) -> int:
    if not raw or not raw.isascii() or not raw.isdigit():
        raise ValueError("Domain rule ports must be numeric.")
    port = int(raw)
    if not 1 <= port <= 65535:
        raise ValueError("Domain rule ports must be between 1 and 65535.")
    return port


def normalize_path_rule(rule: str) -> str:
    """Validate and normalize one absolute or ``~``-based path/glob rule.

    Args:
        rule: Raw configured path or glob.

    Returns:
        The normalized host path expression with platform separators.

    Raises:
        ValueError: If the rule is relative, malformed, or has no traversal
            anchor before its first glob component.
    """
    if not isinstance(rule, str):
        raise ValueError("Filesystem rules must be strings.")
    value = rule.strip()
    if not value:
        raise ValueError("Filesystem rules must not be empty.")
    if any(ord(character) < 0x20 or ord(character) == 0x7F for character in value):
        raise ValueError("Filesystem rules must not contain control characters.")
    if len(value) > MAX_RULE_CHARACTERS:
        raise ValueError(
            f"Filesystem rules must be at most {MAX_RULE_CHARACTERS} characters."
        )
    value = value.replace("\\", "/")
    if ".." in PurePosixPath(value).parts:
        raise ValueError("Filesystem rules must not contain `..` components.")
    if value.endswith("/") and value != "/":
        raise ValueError("Filesystem rules must not end with a separator.")
    if sys.platform == "win32":
        if not (Path(value).is_absolute() or value.startswith("~")):
            raise ValueError("Filesystem rules must be absolute or start with `~`.")
    else:
        if _DRIVE_PREFIX.match(value) or value.startswith("//"):
            raise ValueError("Filesystem rules use a Windows path on this platform.")
        if not (value.startswith("/") or value == "~" or value.startswith("~/")):
            raise ValueError("Filesystem rules must be absolute or start with `~`.")
    _validate_glob_syntax(value)
    expanded = _expand_path(value)
    anchor_text = _literal_anchor(expanded)
    if not anchor_text:
        raise ValueError("Filesystem glob rules require a literal traversal anchor.")
    anchor = Path(anchor_text)
    if not anchor.is_absolute():
        raise ValueError("Filesystem glob rules require an absolute anchor.")
    if _contains_glob(value) and not anchor.exists():
        raise ValueError(
            "Filesystem glob rules require an existing literal traversal anchor."
        )
    return value


def _validate_glob_syntax(value: str) -> None:
    in_bracket = False
    index = 0
    while index < len(value):
        character = value[index]
        if character == "[":
            if in_bracket:
                raise ValueError("Filesystem glob rules contain nested `[`.")
            in_bracket = True
            closing = value.find("]", index + 1)
            if closing < 0:
                raise ValueError("Filesystem glob rules contain an unclosed `[`.")
            content = value[index + 1 : closing]
            if not content or content in {"!", "^"}:
                raise ValueError(
                    "Filesystem glob rules contain an empty character set."
                )
            in_bracket = False
            index = closing
        index += 1


def _contains_glob(value: str) -> bool:
    return any(marker in value for marker in _PATH_MAGIC)


def _literal_anchor(value: str) -> str:
    """Return the literal path prefix before the first glob component."""
    parts = PurePosixPath(value).parts
    literal: list[str] = []
    for part in parts:
        if any(marker in part for marker in _PATH_MAGIC):
            break
        literal.append(part)
    if not literal:
        return ""
    if literal == ["/"]:
        return "/"
    return str(PurePosixPath(*literal))


def _expand_path(value: str) -> str:
    if value == "~" or value.startswith("~/"):
        # abspath is a CodeQL-recognized path normalizer; the result only
        # feeds the literal glob-anchor existence check for a deny rule.
        return os.path.abspath(os.path.expanduser(value))
    return value


def expand_path_rule(rule: str) -> str:
    """Return the host-expanded absolute path expression for a rule."""
    return _expand_path(rule.replace("\\", "/"))


def path_rule_matches(rule: str, path: Path) -> bool:
    """Return whether a configured path or glob rule covers ``path``.

    ``~`` is expanded against the AstrBot account, and ``*``/``?``/``[]``/``**``
    follow ``pathlib.PurePath.full_match`` semantics. Platforms are compared as
    normalized POSIX-style paths so persisted rules remain portable.
    """
    expression = expand_path_rule(rule)
    candidate = str(path)
    if sys.platform == "win32":
        expression = expression.replace("\\", "/")
        candidate = candidate.replace("\\", "/")
    candidate_path = PurePosixPath(candidate)
    expression_path = PurePosixPath(expression)
    if not _contains_glob(expression):
        return candidate_path == expression_path or candidate_path.is_relative_to(
            expression_path
        )
    return candidate_path.full_match(expression)


def sandbox_policy_from_config(
    value: object,
    *,
    role: str,
    platform: str | None = None,
) -> tuple[LocalSandboxPolicy, list[str]]:
    """Parse and validate a persisted role policy.

    Missing nested objects are filled from the role's fresh defaults. Unknown
    keys, malformed types, and unsafe values are reported; a deny rule is never
    silently discarded. At most :data:`MAX_VALIDATION_ERRORS` messages are
    returned.

    Args:
        value: Raw role policy mapping, or None to use defaults.
        role: ``member`` or ``admin`` default row.
        platform: Override for platform-specific socket validation.

    Returns:
        The normalized policy and bounded validation errors.
    """
    platform = platform or sys.platform
    defaults = default_policy(role)
    errors: list[str] = []

    def error(message: str) -> None:
        if len(errors) < MAX_VALIDATION_ERRORS:
            errors.append(message)

    if value is None:
        return defaults, errors
    if not isinstance(value, dict):
        return defaults, ["Local permission policy must be an object."]

    allowed_keys = {
        "allow_execution",
        "filesystem_scope",
        "network",
        "filesystem",
        "unix_sockets",
    }
    for key in value:
        if key not in allowed_keys:
            error(f"Unknown Local permission key `{key}`.")

    allow_execution = value.get("allow_execution", defaults.allow_execution)
    if not isinstance(allow_execution, bool):
        error("allow_execution must be a boolean.")
        allow_execution = defaults.allow_execution

    filesystem_scope = value.get("filesystem_scope", defaults.filesystem_scope)
    if not isinstance(filesystem_scope, str) or filesystem_scope not in (
        _FILESYSTEM_SCOPES
    ):
        error("filesystem_scope must be one of none, workspace, or host.")
        filesystem_scope = defaults.filesystem_scope

    network = _parse_network(value.get("network"), defaults.network, error)
    filesystem = _parse_filesystem(value.get("filesystem"), defaults.filesystem, error)
    unix_sockets = _parse_unix_sockets(
        value.get("unix_sockets"),
        defaults.unix_sockets,
        error,
        platform=platform,
    )

    if filesystem_scope == "none":
        allow_execution = False
    if not allow_execution:
        network = LocalNetworkPolicy(mode="off")
    if network.mode == "off":
        unix_sockets = LocalUnixSocketPolicy(mode="deny")

    policy = LocalSandboxPolicy(
        allow_execution=allow_execution,
        filesystem_scope=filesystem_scope,  # type: ignore[arg-type]
        network=network,
        filesystem=filesystem,
        unix_sockets=unix_sockets,
    )
    return policy, errors


def _parse_network(
    value: object,
    defaults: LocalNetworkPolicy,
    error: Any,
) -> LocalNetworkPolicy:
    if value is None:
        return defaults
    if not isinstance(value, dict):
        error("network must be an object.")
        return defaults
    expected = {
        "mode",
        "allowed_domains",
        "denied_domains",
        "allow_private_network",
        "allow_loopback",
    }
    for key in value:
        if key not in expected:
            error(f"Unknown network policy key `{key}`.")

    mode = value.get("mode", defaults.mode)
    if not isinstance(mode, str) or mode not in _NETWORK_MODES:
        error("network.mode must be one of off, allowlist, or unrestricted.")
        mode = defaults.mode

    allowed = _parse_domain_list(
        value.get("allowed_domains", list(defaults.allowed_domains)),
        "network.allowed_domains",
        error,
    )
    denied = _parse_domain_list(
        value.get("denied_domains", list(defaults.denied_domains)),
        "network.denied_domains",
        error,
    )
    private = value.get("allow_private_network", defaults.allow_private_network)
    if not isinstance(private, bool):
        error("network.allow_private_network must be a boolean.")
        private = defaults.allow_private_network
    loopback = value.get("allow_loopback", defaults.allow_loopback)
    if not isinstance(loopback, bool):
        error("network.allow_loopback must be a boolean.")
        loopback = defaults.allow_loopback
    if mode == "unrestricted":
        allowed = ()
    return LocalNetworkPolicy(
        mode=mode,  # type: ignore[arg-type]
        allowed_domains=allowed,
        denied_domains=denied,
        allow_private_network=private,
        allow_loopback=loopback,
    )


def _parse_domain_list(value: object, label: str, error: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        error(f"{label} must be a list of strings.")
        return ()
    if len(value) > MAX_DOMAIN_RULES:
        error(f"{label} must contain at most {MAX_DOMAIN_RULES} rules.")
    result: list[str] = []
    seen: set[str] = set()
    for entry in value[:MAX_DOMAIN_RULES]:
        try:
            parsed = parse_domain_rule(entry)
        except ValueError as exc:
            error(f"{label}: {exc}")
            continue
        canonical = _format_domain_rule(parsed)
        if canonical not in seen:
            seen.add(canonical)
            result.append(canonical)
    return tuple(result)


def _format_domain_rule(rule: DomainRule) -> str:
    host = f"*.{rule.pattern}" if rule.wildcard else rule.pattern
    if rule.address is not None and isinstance(rule.address, ipaddress.IPv6Address):
        host = f"[{rule.pattern}]"
    if rule.port is not None:
        return f"{host}:{rule.port}"
    return host


def _parse_filesystem(
    value: object,
    defaults: LocalFilesystemPolicy,
    error: Any,
) -> LocalFilesystemPolicy:
    if value is None:
        return defaults
    if not isinstance(value, dict):
        error("filesystem must be an object.")
        return defaults
    for key in value:
        if key not in {"deny_read", "deny_write"}:
            error(f"Unknown filesystem policy key `{key}`.")
    return LocalFilesystemPolicy(
        deny_read=_parse_path_list(
            value.get("deny_read", list(defaults.deny_read)),
            "filesystem.deny_read",
            error,
        ),
        deny_write=_parse_path_list(
            value.get("deny_write", list(defaults.deny_write)),
            "filesystem.deny_write",
            error,
        ),
    )


def _parse_path_list(value: object, label: str, error: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        error(f"{label} must be a list of strings.")
        return ()
    if len(value) > MAX_PATH_RULES:
        error(f"{label} must contain at most {MAX_PATH_RULES} rules.")
    result: list[str] = []
    seen: set[str] = set()
    for entry in value[:MAX_PATH_RULES]:
        try:
            normalized = normalize_path_rule(entry)
        except ValueError as exc:
            error(f"{label}: {exc}")
            continue
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    return tuple(result)


def _parse_unix_sockets(
    value: object,
    defaults: LocalUnixSocketPolicy,
    error: Any,
    *,
    platform: str,
) -> LocalUnixSocketPolicy:
    if value is None:
        return defaults
    if not isinstance(value, dict):
        error("unix_sockets must be an object.")
        return defaults
    for key in value:
        if key not in {"mode", "allowed_paths"}:
            error(f"Unknown unix_sockets policy key `{key}`.")
    mode = value.get("mode", defaults.mode)
    if not isinstance(mode, str) or mode not in _UNIX_SOCKET_MODES:
        error("unix_sockets.mode must be deny or allow_all.")
        mode = defaults.mode
    raw_paths = value.get("allowed_paths", list(defaults.allowed_paths))
    if not isinstance(raw_paths, list):
        error("unix_sockets.allowed_paths must be a list of strings.")
        raw_paths = []
    if len(raw_paths) > MAX_UNIX_PATHS:
        error(
            f"unix_sockets.allowed_paths must contain at most {MAX_UNIX_PATHS} rules."
        )
    paths: list[str] = []
    seen: set[str] = set()
    for entry in raw_paths[:MAX_UNIX_PATHS]:
        if not isinstance(entry, str) or not entry.strip():
            error("unix_sockets.allowed_paths entries must be non-empty strings.")
            continue
        if len(entry) > MAX_RULE_CHARACTERS:
            error(
                "unix_sockets.allowed_paths entries must be at most "
                f"{MAX_RULE_CHARACTERS} characters."
            )
            continue
        if _contains_glob(entry):
            error("unix_sockets.allowed_paths entries must be literal paths.")
            continue
        try:
            normalized = normalize_path_rule(entry)
        except ValueError as exc:
            error(f"unix_sockets.allowed_paths: {exc}")
            continue
        if normalized not in seen:
            seen.add(normalized)
            paths.append(normalized)
    if mode == "allow_all" and paths:
        error("unix_sockets.allowed_paths requires socket mode deny.")
    if platform != "darwin" and paths:
        error("unix_sockets.allowed_paths is supported only on macOS.")
    return LocalUnixSocketPolicy(
        mode=mode,  # type: ignore[arg-type]
        allowed_paths=tuple(paths),
    )


def build_local_network_notice(policy: LocalSandboxPolicy) -> str:
    """Return the bounded prompt notice for a resolved Local policy.

    The notice describes only the policy class and address flags. It never
    includes configured domain names, filesystem paths, or proxy tokens.
    """
    if not policy.allow_execution:
        return (
            "Sandbox policy: Local code execution is disabled for this role. "
            "File tools remain subject to the configured Local access scope."
        )
    if policy.is_native:
        return (
            "Sandbox policy: Local Shell/Python execution runs natively without "
            "operating-system isolation, with host filesystem access and "
            "unrestricted network access. No sandbox guarantee applies."
        )
    if policy.network.mode == "off":
        return (
            "Sandbox policy: Network access is disabled for sandboxed local "
            "Shell/Python execution. Do not retry the same network operation with "
            "another command, Python, HTTP/HTTPS, or disabled certificate "
            "verification; these do not change the policy. Local offline "
            "operations are still allowed."
        )
    if policy.network.mode == "allowlist":
        return (
            "Sandbox policy: Sandboxed local Shell/Python execution uses network "
            "allowlist mode and may reach only policy-approved destinations through "
            "the authenticated AstrBot proxy. "
            "Direct IP and DNS egress is blocked. The proxy verifies HTTPS "
            "certificates normally; do not disable certificate verification or "
            "attempt to bypass the proxy."
        )
    return (
        "Sandbox policy: Sandboxed local Shell/Python execution uses unrestricted "
        "network mode and may reach any policy-permitted destination through the "
        "authenticated AstrBot proxy. "
        "Direct IP and DNS egress is blocked by design. The proxy verifies HTTPS "
        "certificates normally; do not disable certificate verification or "
        "attempt to bypass the proxy."
    )


__all__ = (
    "DomainRule",
    "LocalFilesystemPolicy",
    "LocalNetworkPolicy",
    "LocalSandboxPolicy",
    "LocalUnixSocketPolicy",
    "MAX_DOMAIN_RULES",
    "MAX_PATH_RULES",
    "MAX_RULE_CHARACTERS",
    "MAX_UNIX_PATHS",
    "MAX_VALIDATION_ERRORS",
    "build_local_network_notice",
    "default_policy",
    "default_policy_dict",
    "expand_path_rule",
    "normalize_hostname",
    "normalize_path_rule",
    "parse_domain_rule",
    "path_rule_matches",
    "sandbox_policy_from_config",
)
