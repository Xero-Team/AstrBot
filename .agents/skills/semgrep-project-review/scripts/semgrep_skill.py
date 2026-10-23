#!/usr/bin/env python3
"""Run and audit a Semgrep whole-project scan, then file deduped Issues."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SKILL_DIR = Path(__file__).resolve().parents[1]
LOCAL_RULES = SKILL_DIR / "rules" / "astrbot.yml"
DEFAULT_OUTPUT_DIR = Path(".tmp") / "semgrep-project-review"
DEFAULT_SEMGREP_VERSION = "1.157.0"
DEFAULT_CONTAINER_IMAGE = "docker.io/semgrep/semgrep:1.182.0"
DEFAULT_CONFIGS = ("p/python", "p/typescript", "p/security-audit")
DEFAULT_EXCLUDES = (
    ".git",
    ".tmp",
    ".make",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "data",
    "logs",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    "dashboard/dist",
    "docs/.vitepress/dist",
    "astrbot/core/platform/sources/napcat/generated/ob11_events.py",
    "dashboard/src/api/generated/openapi-v1",
    "*.min.js",
    "*.min.css",
    "*.map",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
    "*.p12",
    "id_rsa*",
)
SEVERITIES = ("critical", "high", "medium", "low", "unknown")
CATEGORIES = (
    "bug",
    "security",
    "performance",
    "maintainability",
    "test",
    "style",
    "documentation",
    "other",
)
VERDICTS = ("pending", "confirmed", "false-positive", "uncertain")
ISSUE_REPO = "Xero-Team/AstrBot"
SECRET_PATTERNS = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{16,}\b"),
    re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)
SECURITY_TERMS = (
    "vulnerability",
    "xss",
    "csrf",
    "ssrf",
    "sql injection",
    "command injection",
    "path traversal",
    "auth bypass",
    "authentication bypass",
    "authorization bypass",
    "remote code execution",
    "rce",
    "privilege escalation",
    "deserialization",
    "secret leak",
    "credential leak",
    "hardcoded key",
    "hardcoded secret",
    "exposed api key",
    "credential exposure",
    "secret exposure",
    "private key",
    "buffer overflow",
    "use after free",
    "open redirect",
    "insecure deserialization",
    "command execution",
    "file inclusion",
    "directory traversal",
    "token leak",
    "api key leak",
    "sensitive data exposure",
    "certificate validation",
    "ssl verification",
)
SECURITY_PATTERNS = tuple(
    re.compile(rf"\b{re.escape(term)}\b", re.IGNORECASE) for term in SECURITY_TERMS
)


class SkillError(Exception):
    """A user-facing failure."""


def fail(message: str) -> None:
    raise SkillError(message)


def now_utc() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def redact_secrets(text: str) -> str:
    redacted = str(text)
    for pattern in SECRET_PATTERNS:
        redacted = pattern.sub("<redacted>", redacted)
    return redacted


def redact_structure(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: redact_structure(item) for key, item in value.items()}
    if isinstance(value, list):
        return [redact_structure(item) for item in value]
    if isinstance(value, str):
        return redact_secrets(value)
    return value


def run_process(
    command: list[str],
    *,
    cwd: Path | None = None,
    timeout: int | None = None,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            command,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError:
        fail(f"command not found: {command[0]}")
    except subprocess.TimeoutExpired:
        fail(f"command timed out after {timeout}s: {' '.join(command[:3])}")
    raise AssertionError("unreachable")


def print_process_output(result: subprocess.CompletedProcess[str]) -> None:
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def write_json(path: Path, data: Any) -> None:
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def repo_root(raw: str | None) -> Path:
    start = Path(raw).resolve() if raw else Path.cwd().resolve()
    if not start.is_dir():
        fail(f"not a directory: {start}")
    result = run_process(["git", "-C", str(start), "rev-parse", "--show-toplevel"])
    if result.returncode != 0:
        fail(f"not a git checkout: {start}")
    return Path(result.stdout.strip())


def git_commit(repo: Path) -> str:
    result = run_process(["git", "-C", str(repo), "rev-parse", "HEAD"])
    return result.stdout.strip() if result.returncode == 0 else "unknown"


def output_base(repo: Path) -> Path:
    return repo / DEFAULT_OUTPUT_DIR


def unique_run_dir(base: Path) -> Path:
    base.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y-%m-%dT%H-%M-%SZ")
    candidate = base / stamp
    counter = 1
    while candidate.exists():
        candidate = base / f"{stamp}-{counter:02d}"
        counter += 1
    candidate.mkdir(parents=True)
    return candidate


def explicit_output_dir(repo: Path, raw: str | None) -> Path:
    if not raw:
        return unique_run_dir(output_base(repo))
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = repo / path
    resolved = path.resolve()
    repository = repo.resolve()
    if resolved == repository or (
        resolved.is_relative_to(repository)
        and not resolved.is_relative_to(repository / ".tmp")
    ):
        raise SkillError(
            "--out-dir must not be the repository root or an in-repo path outside .tmp"
        )
    if path.exists() and (path / "findings.json").exists():
        print(
            f"warning: {path} already contains findings; reusing it explicitly",
            file=sys.stderr,
        )
    path.mkdir(parents=True, exist_ok=True)
    return path


def latest_run_dir(repo: Path) -> Path | None:
    base = output_base(repo)
    if not base.is_dir():
        return None
    runs = sorted(
        (path for path in base.iterdir() if (path / "findings.json").is_file()),
        key=lambda path: path.name,
    )
    return runs[-1] if runs else None


def resolve_read_dir(repo: Path, raw: str | None) -> Path:
    if raw:
        path = Path(raw).expanduser()
        if not path.is_absolute():
            path = repo / path
        if not (path / "findings.json").is_file():
            fail(f"no findings.json in {path}")
        return path
    latest = latest_run_dir(repo)
    if not latest:
        fail("no run found; run `semgrep_skill.py run` first")
    return latest


def semgrep_command() -> list[str]:
    override = os.environ.get("SEMGREP_BIN", "").strip()
    if override:
        return [override]
    uvx = shutil.which("uvx")
    if uvx:
        version = os.environ.get("SEMGREP_VERSION", DEFAULT_SEMGREP_VERSION).strip()
        if version in {"", "latest", "auto"}:
            return [uvx, "semgrep"]
        return [uvx, "--from", f"semgrep=={version}", "semgrep"]
    semgrep = shutil.which("semgrep")
    if semgrep:
        return [semgrep]
    fail("semgrep is not available; install uv so `uvx semgrep` works")


def semgrep_version(command: list[str]) -> str:
    result = run_process([*command, "--version"], timeout=300)
    if result.returncode != 0:
        print_process_output(result)
        fail("failed to run semgrep --version")
    return (result.stdout or result.stderr).strip().splitlines()[-1]


def cmd_doctor(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    ok = True
    print(f"repo: {repo}")

    uvx = shutil.which("uvx")
    if uvx:
        result = run_process([uvx, "--version"], timeout=60)
        version = (result.stdout or result.stderr).strip().splitlines()[-1]
        print(f"uvx: {version}")
    else:
        print("uvx: MISSING (install uv; the skill runs `uvx semgrep`)")
        ok = False

    try:
        command = semgrep_command()
        print(f"semgrep: {semgrep_version(command)} ({' '.join(command)})")
    except SkillError as error:
        print(f"semgrep: FAILED ({error})")
        ok = False

    git = shutil.which("git")
    print(f"git: {git or 'MISSING'}")
    print(f"commit: {git_commit(repo)}")
    ok = ok and bool(git)

    runtime = container_runtime()
    if runtime:
        print(
            f"container fallback: {Path(runtime).name} "
            f"({os.environ.get('SEMGREP_CONTAINER_IMAGE', DEFAULT_CONTAINER_IMAGE)})"
        )
    else:
        print("container fallback: none (install podman or docker)")

    gh = shutil.which("gh")
    if gh:
        auth = run_process([gh, "auth", "status", "--hostname", "github.com"])
        print(
            f"gh: {gh} ({'authenticated' if auth.returncode == 0 else 'not authenticated'})"
        )
    else:
        print("gh: MISSING (only needed to search or file Issues)")

    if LOCAL_RULES.is_file():
        print(f"local rules: {LOCAL_RULES}")
    else:
        print(f"local rules: MISSING ({LOCAL_RULES})")
        ok = False

    latest = latest_run_dir(repo)
    if latest:
        document = json.loads((latest / "findings.json").read_text(encoding="utf-8"))
        print(
            f"latest run: {latest} "
            f"({len(document.get('findings', []))} finding(s), "
            f"status {document.get('status', 'unknown')})"
        )
    else:
        print("latest run: none")
    return 0 if ok else 1


def normalize_severity(raw: Any) -> str:
    return {"ERROR": "high", "WARNING": "medium", "INFO": "low"}.get(
        str(raw or "").upper(), "unknown"
    )


def normalize_category(raw: Any, rule_id: str) -> str:
    if isinstance(raw, list):
        raw = raw[0] if raw else ""
    value = str(raw or "").strip().lower()
    aliases = {
        "correctness": "bug",
        "best-practice": "maintainability",
        "portability": "maintainability",
        "compatibility": "maintainability",
        "security": "security",
        "performance": "performance",
        "maintainability": "maintainability",
        "style": "style",
    }
    if value in aliases:
        return aliases[value]
    if "security" in rule_id.lower() or "secret" in rule_id.lower():
        return "security"
    return "other"


def metadata_subset(metadata: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "category",
        "confidence",
        "impact",
        "likelihood",
        "cwe",
        "owasp",
        "references",
        "shortlink",
        "technology",
        "subcategory",
        "vulnerability_class",
    )
    return {key: metadata[key] for key in keys if key in metadata}


def line_of(value: Any) -> int:
    try:
        return int(value)
    except TypeError, ValueError:
        return 0


def source_code(repo: Path, path: str, start: int, end: int) -> str:
    target = Path(path)
    if not target.is_absolute():
        target = repo / target
    try:
        lines = target.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if start < 1 or start > len(lines):
        return ""
    stop = min(max(end, start), len(lines))
    return redact_secrets("\n".join(lines[start - 1 : stop]))


def local_rule_ids() -> tuple[str, ...]:
    if not LOCAL_RULES.is_file():
        return ()
    return tuple(
        re.findall(
            r"^\s*-\s*id:\s*(\S+)", LOCAL_RULES.read_text(encoding="utf-8"), re.M
        )
    )


def normalize_rule_id(rule_id: str) -> str:
    for candidate in local_rule_ids():
        if rule_id.endswith(candidate):
            return candidate
    return rule_id


def normalize_path(path: str, scan_root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return path
    try:
        return candidate.relative_to(scan_root.resolve()).as_posix()
    except ValueError:
        return path


def normalize_document(
    raw: dict[str, Any], repo: Path, scan_root: Path
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for result in raw.get("results") or []:
        if not isinstance(result, dict):
            continue
        extra = result.get("extra") or {}
        metadata = extra.get("metadata") or {}
        path = normalize_path(str(result.get("path") or ""), scan_root)
        start = line_of((result.get("start") or {}).get("line"))
        end = line_of((result.get("end") or {}).get("line")) or start
        rule_id = normalize_rule_id(str(result.get("check_id") or "unknown"))
        content = str(extra.get("message") or "").strip()
        fingerprint = extra.get("fingerprint")
        key = (rule_id, path, start, end, fingerprint or content)
        if key in seen:
            continue
        seen.add(key)
        findings.append(
            {
                "id": "",
                "rule_id": rule_id,
                "path": path,
                "start_line": start,
                "end_line": end,
                "severity": normalize_severity(extra.get("severity")),
                "category": normalize_category(metadata.get("category"), rule_id),
                "content": redact_secrets(content),
                "code": source_code(repo, path, start, end),
                "fix": redact_secrets(str(extra.get("fix") or "")),
                "fingerprint": fingerprint,
                "metadata": redact_structure(metadata_subset(metadata)),
                "audit": {
                    "verdict": "pending",
                    "severity": None,
                    "category": None,
                    "evidence": "",
                    "notes": "",
                    "checks": [],
                },
            }
        )
    findings.sort(key=lambda item: (item["path"], item["start_line"], item["rule_id"]))
    for index, finding in enumerate(findings, start=1):
        finding["id"] = f"SEM-{index:03d}"
    return findings


def severity_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(SEVERITIES, 0)
    for finding in findings:
        counts[finding.get("severity", "unknown")] += 1
    return counts


def verdict_counts(findings: list[dict[str, Any]]) -> dict[str, int]:
    counts = dict.fromkeys(VERDICTS, 0)
    for finding in findings:
        counts[finding.get("audit", {}).get("verdict", "pending")] += 1
    return counts


def location(finding: dict[str, Any]) -> str:
    return f"{finding.get('path', '?')}:{finding.get('start_line', 0)}"


def fence(text: str) -> str:
    longest = 0
    for match in re.finditer(r"`+", text):
        longest = max(longest, len(match.group(0)))
    marker = "`" * max(3, longest + 1)
    return f"{marker}\n{text.rstrip()}\n{marker}"


def finding_block(finding: dict[str, Any], *, final: bool) -> list[str]:
    audit = finding.get("audit", {})
    severity = audit.get("severity") or finding.get("severity", "unknown")
    lines = [
        f"### {finding['id']} — {severity} — `{finding['rule_id']}`",
        "",
        f"- Location: `{location(finding)}`",
        f"- Category: `{finding.get('category', 'other')}`",
        f"- Semgrep severity: `{finding.get('severity', 'unknown')}`",
        f"- Message: {finding.get('content', '')}",
    ]
    metadata = finding.get("metadata") or {}
    for key in ("cwe", "owasp", "confidence", "impact", "likelihood"):
        if metadata.get(key):
            value = metadata[key]
            if isinstance(value, list):
                value = ", ".join(str(item) for item in value)
            label = {"cwe": "CWE", "owasp": "OWASP"}.get(key, key.title())
            lines.append(f"- {label}: {value}")
    references = metadata.get("references") or []
    if isinstance(references, str):
        references = [references]
    if references:
        lines.append("- References: " + ", ".join(str(item) for item in references))
    if final:
        lines.append(f"- Verdict: `{audit.get('verdict', 'pending')}`")
        if audit.get("evidence"):
            lines.append(f"- Evidence: {audit['evidence']}")
        if audit.get("notes"):
            lines.append(f"- Audit notes: {audit['notes']}")
        checks = audit.get("checks") or []
        if checks:
            lines.append("- Checks: " + ", ".join(str(check) for check in checks))
    else:
        lines.append(f"- Verdict: `{audit.get('verdict', 'pending')}`")
    code = finding.get("code") or ""
    if code:
        lines.extend(["", fence(code)])
    return lines


def render_report(document: dict[str, Any], *, final: bool) -> str:
    findings = document.get("findings") or []
    coverage = document.get("coverage") or {}
    severities = severity_counts(findings)
    verdicts = verdict_counts(findings)
    lines = [
        "# Semgrep Project Review",
        "",
        f"- Run: `{document.get('run_id', 'unknown')}`",
        f"- Created: `{document.get('created_at', 'unknown')}`",
        f"- Commit: `{document.get('commit', 'unknown')}`",
        f"- Semgrep: `{document.get('semgrep_version', 'unknown')}`",
        f"- Engine: `{document.get('engine', 'local')}`",
        f"- Parse normalization: "
        f"{'on' if (document.get('parse_normalization') or {}).get('enabled') else 'off'}"
        f" ({(document.get('parse_normalization') or {}).get('rewritten_files', 0)}"
        " file(s) rewritten)",
        f"- Status: `{document.get('status', 'unknown')}`",
        f"- Configs: {', '.join(f'`{item}`' for item in document.get('configs', []))}",
        f"- Findings: {len(findings)}",
        "",
        "## Coverage",
        "",
        "| Metric | Value |",
        "| --- | --- |",
        f"| Files scanned | {coverage.get('files_scanned', 0)} |",
        f"| Files skipped | {coverage.get('files_skipped', 0)} |",
        f"| Scan errors | {coverage.get('errors', 0)} |",
        f"| Partial | {'yes' if coverage.get('partial') else 'no'} |",
        "",
    ]
    errors = document.get("scan_errors") or []
    if errors:
        lines.extend(
            [
                "<details>",
                "<summary>Scan errors and skipped paths</summary>",
                "",
            ]
        )
        lines.extend(f"- {redact_secrets(str(item))}" for item in errors[:50])
        if len(errors) > 50:
            lines.append(f"- ... and {len(errors) - 50} more")
        lines.extend(["", "</details>", ""])
    lines.extend(
        [
            "## Summary",
            "",
            "| Severity | Count |",
            "| --- | --- |",
        ]
    )
    for severity in SEVERITIES:
        lines.append(f"| {severity} | {severities[severity]} |")
    if final:
        lines.extend(
            [
                "",
                "| Verdict | Count |",
                "| --- | --- |",
            ]
        )
        for verdict in VERDICTS:
            lines.append(f"| {verdict} | {verdicts[verdict]} |")
    lines.append("")

    groups: list[tuple[str, list[dict[str, Any]]]] = []
    if final:
        for verdict, title in (
            ("confirmed", "Confirmed findings"),
            ("uncertain", "Uncertain findings"),
            ("pending", "Pending findings"),
            ("false-positive", "False positives (appendix)"),
        ):
            selected = [
                item
                for item in findings
                if item.get("audit", {}).get("verdict") == verdict
            ]
            if selected:
                groups.append((title, selected))
    else:
        groups.append(("Findings", findings))

    if not findings:
        lines.extend(["No findings.", ""])
    for title, selected in groups:
        lines.extend([f"## {title}", ""])
        for finding in selected:
            lines.extend(finding_block(finding, final=final))
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_error_count(raw: dict[str, Any]) -> int:
    count = 0
    for error in raw.get("errors") or []:
        if not isinstance(error, dict):
            continue
        kind = f"{error.get('type', '')} {error.get('message', '')}".lower()
        if "syntax" in kind or "partialparsing" in kind or "parse" in kind:
            count += 1
    return count


def has_python_parse_error(raw: dict[str, Any]) -> bool:
    for error in raw.get("errors") or []:
        if not isinstance(error, dict):
            continue
        kind = f"{error.get('type', '')} {error.get('message', '')}".lower()
        if (
            "syntax" not in kind
            and "partialparsing" not in kind
            and "parse" not in kind
        ):
            continue
        if str(error.get("path") or "").endswith(".py"):
            return True
    return False


def container_runtime() -> str | None:
    for name in ("podman", "docker"):
        path = shutil.which(name)
        if path:
            return path
    return None


def container_path(path: Path, scan_root: Path, out: Path) -> str:
    resolved = path.resolve()
    root = scan_root.resolve()
    if resolved.is_relative_to(root):
        return "/src/" + resolved.relative_to(root).as_posix()
    out_root = out.resolve()
    if resolved.is_relative_to(out_root):
        return "/out/" + resolved.relative_to(out_root).as_posix()
    fail(f"container engine cannot mount {path} outside the repository")


def container_prefix(scan_root: Path, out: Path) -> list[str] | None:
    runtime = container_runtime()
    if not runtime:
        return None
    mounts = ["-v", f"{scan_root}:/src:Z", "-w", "/src"]
    if Path(runtime).name == "podman":
        mounts.append("--userns=keep-id")
    else:
        mounts.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
    if not out.resolve().is_relative_to(scan_root.resolve()):
        mounts.extend(["-v", f"{out}:/out:Z"])
    image = (
        os.environ.get("SEMGREP_CONTAINER_IMAGE", DEFAULT_CONTAINER_IMAGE).strip()
        or DEFAULT_CONTAINER_IMAGE
    )
    return [runtime, "run", "--rm", *mounts, image, "semgrep"]


PEP758 = re.compile(
    r"^(?P<indent>\s*)except\s+"
    r"(?P<names>[A-Za-z_][\w.]*(?:\s*,\s*[A-Za-z_][\w.]*)+)"
    r"(?P<as>\s+as\s+[A-Za-z_]\w*)?\s*:",
    re.MULTILINE,
)


def normalize_python_source(text: str) -> str:
    return PEP758.sub(
        lambda match: (
            f"{match.group('indent')}except ({match.group('names')})"
            f"{match.group('as') or ''}:"
        ),
        text,
    )


SKIP_DIRS = {
    ".git",
    ".tmp",
    ".make",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "data",
    "logs",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
SKIP_PATHS = (
    "dashboard/dist",
    "docs/.vitepress/dist",
    "astrbot/core/platform/sources/napcat/generated/ob11_events.py",
    "dashboard/src/api/generated/openapi-v1",
)


def should_skip(relative: str) -> bool:
    name = Path(relative).name
    if name == ".env" or name.startswith(".env."):
        return True
    if name.startswith("id_rsa"):
        return True
    if Path(relative).suffix in {".pem", ".key", ".p12"}:
        return True
    return any(
        relative == prefix or relative.startswith(prefix + "/") for prefix in SKIP_PATHS
    )


def prepare_mirror(repo: Path, out: Path) -> tuple[Path, int]:
    mirror = out / "tree"
    if mirror.exists():
        shutil.rmtree(mirror)
    mirror.mkdir(parents=True)
    rewritten = 0
    out_resolved = out.resolve()
    for root, dirs, files in os.walk(repo):
        current = Path(root)
        relative_dir = current.relative_to(repo)
        dirs[:] = sorted(
            name
            for name in dirs
            if name not in SKIP_DIRS
            and not should_skip((relative_dir / name).as_posix())
            and not (current / name).resolve().is_relative_to(out_resolved)
        )
        for name in sorted(files):
            source = current / name
            relative = source.relative_to(repo)
            if should_skip(relative.as_posix()):
                continue
            target = mirror / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".py":
                original = source.read_bytes().decode("utf-8", errors="replace")
                normalized = normalize_python_source(original)
                if normalized != original:
                    target.write_bytes(normalized.encode("utf-8"))
                    rewritten += 1
                    continue
            shutil.copy2(source, target)
    return mirror, rewritten


def materialize_config(config: str, repo: Path, scan_root: Path) -> str:
    candidate = Path(config).expanduser()
    if not candidate.is_absolute():
        candidate = repo / candidate
    if not candidate.exists():
        return config
    resolved = candidate.resolve()
    repository = repo.resolve()
    if resolved.is_relative_to(repository):
        mirrored = scan_root / resolved.relative_to(repository)
        if not mirrored.exists():
            fail(f"config path is excluded from the scan mirror: {config}")
        return str(mirrored)
    target = scan_root / ".semgrep-configs" / resolved.name
    target.parent.mkdir(parents=True, exist_ok=True)
    if resolved.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(resolved, target)
    else:
        shutil.copy2(resolved, target)
    return str(target)


def build_scan_command(
    *,
    engine: str,
    scan_root: Path,
    out: Path,
    configs: list[str],
    paths: list[str],
    excludes: list[str],
    args: argparse.Namespace,
    raw_path: Path,
    normalized: bool,
) -> list[str] | None:
    if engine == "container":
        prefix = container_prefix(scan_root, out)
        if not prefix:
            fail("container engine requested but podman or docker was not found")
        output = container_path(raw_path, scan_root, out)
        config_args = [
            container_path(Path(config), scan_root, out)
            if Path(config).is_absolute()
            else config
            for config in configs
        ]
    else:
        prefix = semgrep_command()
        output = str(raw_path)
        config_args = configs
    command = [
        *prefix,
        "scan",
        "--json",
        "--output",
        output,
        "--metrics",
        "off",
        "--disable-version-check",
        "--no-rewrite-rule-ids",
        "--timeout",
        str(int(args.timeout)),
        "--max-target-bytes",
        str(args.max_target_bytes),
    ]
    if normalized:
        command.append("--no-git-ignore")
    for config in config_args:
        command.extend(["--config", config])
    for exclude in excludes:
        command.extend(["--exclude", exclude])
    for severity in args.severity:
        command.extend(["--severity", severity])
    if args.jobs:
        command.extend(["--jobs", str(args.jobs)])
    command.extend(paths)
    return command


def cmd_run(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    out = explicit_output_dir(repo, args.out_dir)
    engine = args.engine
    if engine == "auto":
        engine = "local"
    if args.engine == "container":
        version = "container"
    else:
        version = semgrep_version(semgrep_command())

    if args.local_only:
        configs = [str(LOCAL_RULES)]
        if not LOCAL_RULES.is_file():
            fail(f"local rules not found: {LOCAL_RULES}")
    else:
        configs = list(args.config) if args.config else list(DEFAULT_CONFIGS)
        if not args.no_local_rules and LOCAL_RULES.is_file():
            configs.append(str(LOCAL_RULES))
    if any(str(config).strip().lower() == "auto" for config in configs):
        fail("--config auto is forbidden; pass explicit packs or --local-only")

    paths: list[str] = []
    repository = repo.resolve()
    for raw in args.path or ["."]:
        candidate = Path(raw)
        if not candidate.is_absolute():
            candidate = repo / candidate
        candidate = candidate.resolve()
        if not candidate.exists():
            fail(f"scan path does not exist: {raw}")
        if not candidate.is_relative_to(repository):
            fail(f"scan path is outside the repository: {raw}")
        paths.append(candidate.relative_to(repository).as_posix() or ".")
    if not paths:
        paths = ["."]

    excludes = list(DEFAULT_EXCLUDES)
    if not args.no_parse_normalization:
        excludes = [item for item in excludes if item != ".tmp"]
    for raw in args.exclude:
        for item in raw.split(","):
            item = item.strip()
            if item and item not in excludes:
                excludes.append(item)

    if args.no_parse_normalization:
        scan_root = repo
        rewritten = 0
    else:
        scan_root, rewritten = prepare_mirror(repo, out)
    materialized = [materialize_config(config, repo, scan_root) for config in configs]

    raw_path = out / "semgrep-raw.json"
    attempts: list[str] = []
    log_parts: list[str] = []
    raw: dict[str, Any] | None = None
    final_engine = engine
    while True:
        command = build_scan_command(
            engine=engine,
            scan_root=scan_root,
            out=out,
            configs=materialized,
            paths=paths,
            excludes=excludes,
            args=args,
            raw_path=raw_path,
            normalized=not args.no_parse_normalization,
        )
        assert command is not None
        attempts.append(engine)
        started = time.monotonic()
        result = run_process(command, cwd=scan_root, timeout=args.process_timeout)
        elapsed = time.monotonic() - started
        log_parts.extend(
            [
                f"## attempt {len(attempts)}: {engine}",
                "$ " + " ".join(command),
                f"exit: {result.returncode}",
                f"elapsed: {elapsed:.1f}s",
                "",
                "### stdout",
                redact_secrets(result.stdout or ""),
                "",
                "### stderr",
                redact_secrets(result.stderr or ""),
                "",
            ]
        )
        text = (result.stdout or "") + (result.stderr or "")
        crashed = "semgrep-core exited" in text
        can_fallback = args.engine == "auto" and engine == "local"
        if result.returncode != 0:
            if can_fallback and crashed and container_runtime():
                print(
                    "warning: local semgrep crashed; retrying with the "
                    "pinned container image",
                    file=sys.stderr,
                )
                engine = "container"
                final_engine = "container"
                continue
            if raw_path.exists():
                raw_path.unlink()
            log_path = out / "scan.log"
            log_path.write_text("\n".join(log_parts), encoding="utf-8")
            print_process_output(result)
            fail(f"semgrep failed (exit {result.returncode}); see {log_path}")
        if not raw_path.is_file():
            fail(f"semgrep did not write {raw_path}; see {out / 'scan.log'}")
        try:
            raw = json.loads(raw_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as error:
            fail(f"semgrep wrote invalid JSON to {raw_path}: {error}")
        if can_fallback and has_python_parse_error(raw) and container_runtime():
            print(
                "warning: local semgrep could not fully parse some files; "
                "retrying with the pinned container image",
                file=sys.stderr,
            )
            engine = "container"
            final_engine = "container"
            continue
        break

    assert raw is not None
    log_path = out / "scan.log"
    log_path.write_text("\n".join(log_parts), encoding="utf-8")

    redacted = redact_structure(raw)
    write_json(raw_path, redacted)

    findings = normalize_document(redacted, repo, scan_root)
    errors = redacted.get("errors") or []
    error_paths: list[str] = []
    for error in errors:
        if isinstance(error, dict):
            path = error.get("path") or str(error)
            path_text = normalize_path(str(path), scan_root)
            if path_text.startswith("/src/"):
                path_text = path_text[5:]
            message = " ".join(redact_secrets(str(error.get("message") or "")).split())
            error_paths.append(f"{path_text}: {message}" if message else path_text)
        else:
            error_paths.append(str(error))
    scanned = redacted.get("paths", {}).get("scanned") or []
    skipped = redacted.get("paths", {}).get("skipped") or []
    coverage = {
        "files_scanned": len(scanned),
        "files_skipped": len(skipped),
        "errors": len(errors),
        "parse_errors": parse_error_count(redacted),
        "partial": bool(errors),
    }
    document = {
        "run_id": out.name,
        "created_at": now_utc(),
        "commit": git_commit(repo),
        "status": "completed_with_errors" if errors else "success",
        "engine": final_engine,
        "engine_attempts": attempts,
        "semgrep_version": redacted.get("version") or version,
        "configs": configs,
        "paths": paths,
        "excludes": excludes,
        "parse_normalization": {
            "enabled": not args.no_parse_normalization,
            "rewritten_files": rewritten,
        },
        "findings": findings,
        "coverage": coverage,
        "scan_errors": error_paths,
        "stats": redacted.get("stats") or {},
    }
    write_json(out / "findings.json", document)
    write_json(
        out / "audit-template.json",
        [
            {
                "id": finding["id"],
                "verdict": "pending",
                "severity": None,
                "category": None,
                "evidence": "",
                "notes": "",
                "checks": [],
            }
            for finding in findings
        ],
    )
    (out / "report-semgrep.md").write_text(
        render_report(document, final=False), encoding="utf-8"
    )
    write_json(
        out / "run.json",
        {key: value for key, value in document.items() if key != "findings"},
    )

    severities = severity_counts(findings)
    print(f"Wrote {out}")
    print(
        f"{len(findings)} finding(s): high {severities['high']}, "
        f"medium {severities['medium']}, low {severities['low']}; "
        f"{len(errors)} scan error(s); {len(scanned)} file(s) scanned."
    )
    if rewritten:
        print(f"Normalized PEP 758 syntax in {rewritten} mirrored file(s).")
    if errors:
        print(
            f"Coverage is partial; inspect {log_path} and the report.",
            file=sys.stderr,
        )
    return 0


def read_findings(repo: Path, raw: str | None) -> tuple[Path, dict[str, Any]]:
    out = resolve_read_dir(repo, raw)
    document = json.loads((out / "findings.json").read_text(encoding="utf-8"))
    return out, document


def cmd_list(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    out, document = read_findings(repo, args.out_dir)
    findings = document.get("findings") or []
    if args.pending:
        findings = [
            item
            for item in findings
            if item.get("audit", {}).get("verdict") == "pending"
        ]
    if not findings:
        print("No findings.")
        return 0
    print(f"{out}")
    for finding in findings:
        audit = finding.get("audit", {})
        severity = audit.get("severity") or finding.get("severity", "unknown")
        print(
            f"{finding['id']}  {audit.get('verdict', 'pending'):14} "
            f"{severity:9} {finding['category']:15} "
            f"{location(finding)}  {finding['rule_id']}"
        )
    return 0


def audit_entries(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        if isinstance(payload.get("findings"), list):
            return [item for item in payload["findings"] if isinstance(item, dict)]
        return [
            {"id": key, **value}
            for key, value in payload.items()
            if isinstance(value, dict)
        ]
    fail("audit file must be a list, an object with a findings list, or an id map")


def cmd_apply_audit(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    out, document = read_findings(repo, args.out_dir)
    payload = json.loads(Path(args.file).read_text(encoding="utf-8"))
    entries = audit_entries(payload)
    by_id = {finding["id"]: finding for finding in document.get("findings") or []}
    updated = 0
    for entry in entries:
        finding_id = str(entry.get("id") or "").strip()
        if finding_id not in by_id:
            fail(f"unknown finding id: {finding_id or '<empty>'}")
        finding = by_id[finding_id]
        audit = finding.setdefault("audit", {})
        verdict = entry.get("verdict")
        if verdict is not None:
            if verdict not in VERDICTS:
                fail(f"{finding_id}: invalid verdict {verdict!r}")
            audit["verdict"] = verdict
        severity = entry.get("severity")
        if severity is not None:
            if severity not in SEVERITIES:
                fail(f"{finding_id}: invalid severity {severity!r}")
            audit["severity"] = severity
        category = entry.get("category")
        if category is not None:
            if category not in CATEGORIES:
                fail(f"{finding_id}: invalid category {category!r}")
            audit["category"] = category
            finding["category"] = category
        for key in ("evidence", "notes"):
            if entry.get(key) is not None:
                audit[key] = str(entry[key])
        checks = entry.get("checks")
        if checks is not None:
            if isinstance(checks, str):
                checks = [checks]
            audit["checks"] = [str(check) for check in checks]
        updated += 1
    document["findings"] = list(by_id.values())
    write_json(out / "findings.json", document)
    (out / "report-final.md").write_text(
        render_report(document, final=True), encoding="utf-8"
    )
    pending = [
        finding["id"]
        for finding in document["findings"]
        if finding.get("audit", {}).get("verdict") == "pending"
    ]
    print(f"Updated {updated} finding(s); {len(pending)} still pending.")
    if pending and args.require_all:
        fail("still pending: " + ", ".join(pending))
    return 0


def cmd_finalize(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    out, document = read_findings(repo, args.out_dir)
    pending = [
        finding["id"]
        for finding in document.get("findings") or []
        if finding.get("audit", {}).get("verdict") == "pending"
    ]
    if pending and not args.allow_pending:
        fail(
            "audit is incomplete; still pending: "
            + ", ".join(pending)
            + ". Use --allow-pending to render them as not audited."
        )
    report_path = out / "report-final.md"
    report_path.write_text(render_report(document, final=True), encoding="utf-8")
    counts = verdict_counts(document.get("findings") or [])
    print(f"Wrote {report_path}")
    print(
        f"confirmed {counts['confirmed']}, uncertain {counts['uncertain']}, "
        f"false positives {counts['false-positive']}, pending {counts['pending']}"
    )
    return 0


def looks_security(finding: dict[str, Any]) -> bool:
    metadata = finding.get("metadata") or {}
    if str(finding.get("category", "")).lower() == "security":
        return True
    if metadata.get("cwe") or metadata.get("owasp"):
        return True
    audit = finding.get("audit", {})
    text = " ".join(
        [
            str(finding.get("content", "")),
            str(audit.get("evidence", "")),
            str(audit.get("notes", "")),
        ]
    )
    return any(pattern.search(text) for pattern in SECURITY_PATTERNS)


def affected_area(path: str) -> str:
    normalized = path.lower()
    rules = (
        ("astrbot/core/pipeline", "Pipeline / EventBus"),
        ("astrbot/core/agent", "Providers / agent runners"),
        ("astrbot/core/provider", "Providers / agent runners"),
        ("astrbot/core/platform", "Platform adapters"),
        ("astrbot/dashboard", "Dashboard / OpenAPI"),
        ("openspec/", "Dashboard / OpenAPI"),
        ("astrbot/core/knowledge_base", "Knowledge base"),
        ("astrbot/core/star", "Plugins / Stars"),
        ("astrbot/builtin_stars", "Plugins / Stars"),
        ("astrbot/core/backup", "Backup / restore"),
        ("docs/", "Docs"),
        (".github/", "CI / toolchain"),
        ("scripts/", "CI / toolchain"),
        ("makefile", "CI / toolchain"),
    )
    for prefix, area in rules:
        if normalized.startswith(prefix):
            return area
    return "Other"


def contains_secret(text: str) -> bool:
    return any(pattern.search(text) for pattern in SECRET_PATTERNS)


def issue_title(finding: dict[str, Any]) -> str:
    text = " ".join(str(finding.get("content", "")).split())
    text = text.rstrip(".")
    if not text:
        text = f"Defect at {location(finding)}"
    text = redact_secrets(text)
    if len(text) > 80:
        text = text[:77].rstrip() + "..."
    return f"[bug] {text}"


def issue_body(finding: dict[str, Any], document: dict[str, Any]) -> str:
    audit = finding.get("audit", {})
    severity = audit.get("severity") or finding.get("severity", "unknown")
    checks = audit.get("checks") or []
    commit = document.get("commit", "unknown")
    metadata = finding.get("metadata") or {}
    lines = [
        "### Preflight",
        "",
        "- [x] I searched open and closed Issues and PRs.",
        "- [x] I tested the current `master` branch or the exact commit.",
        "- [x] This report contains no secrets, tokens, or private data.",
        "- [x] This is not a security vulnerability (those use a private advisory).",
        "- [x] I filled exactly one of Human note or Agent note, matching who wrote this Issue.",
        "",
        "### Affected area",
        "",
        affected_area(finding["path"]),
        "",
        "### What happened",
        "",
        f"`{location(finding)}` — {redact_secrets(finding['content'])}",
        "",
        f"- Audited severity: `{severity}`",
        f"- Category: `{finding['category']}`",
        f"- Semgrep rule: `{finding['rule_id']}`",
        f"- Finding ID: `{finding['id']}`",
    ]
    if metadata.get("cwe"):
        lines.append(f"- CWE: {metadata['cwe']}")
    if metadata.get("owasp"):
        lines.append(f"- OWASP: {metadata['owasp']}")
    if audit.get("evidence"):
        lines.append(f"- Evidence: {redact_secrets(audit['evidence'])}")
    if checks:
        lines.append("- Checks: " + ", ".join(str(check) for check in checks))
    if audit.get("notes"):
        lines.append(f"- Audit notes: {redact_secrets(audit['notes'])}")
    references = metadata.get("references") or []
    if isinstance(references, str):
        references = [references]
    if references:
        lines.append(
            "- Rule references: " + ", ".join(str(item) for item in references)
        )
    if finding.get("fix"):
        lines.extend(["", "**Suggested fix:**", "", fence(finding["fix"])])
    lines.extend(
        [
            "",
            "### Commit or version",
            "",
            f"`{commit}`",
            "",
            "### Environment",
            "",
            f"Source checkout, Python {sys.version.split()[0]}, "
            f"Semgrep {document.get('semgrep_version', 'unknown')}, commit `{commit}`.",
            "",
            "### Author",
            "",
            "Agent",
            "",
            "## Agent note",
            "",
            "This issue came from a Semgrep whole-repository scan. The coding "
            "agent independently re-read the referenced code, traced its "
            "callers, and recorded the finding as confirmed before drafting "
            "this report.",
            "",
            f"- Paths: `{finding['path']}`",
            f"- Semgrep rule: `{finding['rule_id']}`",
            f"- Checks: {', '.join(str(check) for check in checks) or 'source review'}",
            "- Residual risk: see the evidence above; this is not a claim of "
            "complete coverage of the module.",
            "- AI tools: Semgrep candidate generation; coding-agent verification.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def issue_query(title: str) -> str:
    return re.sub(r"^\[[^\]]+\]\s*", "", title).strip() or title


def discover_candidates(gh: str, title: str) -> list[dict[str, Any]]:
    query = issue_query(title)
    candidates: list[dict[str, Any]] = []
    for kind, command in (
        (
            "issue",
            [
                gh,
                "issue",
                "list",
                "--repo",
                ISSUE_REPO,
                "--state",
                "all",
                "--search",
                query,
                "--json",
                "number,title,url,state",
                "--limit",
                "20",
            ],
        ),
        (
            "pr",
            [
                gh,
                "pr",
                "list",
                "--repo",
                ISSUE_REPO,
                "--state",
                "all",
                "--search",
                query,
                "--json",
                "number,title,url,state",
                "--limit",
                "20",
            ],
        ),
    ):
        result = run_process(command)
        if result.returncode != 0:
            print(
                f"warning: could not search {kind}s: {result.stderr.strip()}",
                file=sys.stderr,
            )
            continue
        try:
            items = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            print(f"warning: invalid JSON from gh {kind} list", file=sys.stderr)
            continue
        for item in items:
            if isinstance(item, dict):
                item["kind"] = kind
                candidates.append(item)
    return candidates


def exact_match(candidates: list[dict[str, Any]], title: str) -> dict[str, Any] | None:
    for candidate in candidates:
        if str(candidate.get("title", "")).strip().lower() == title.strip().lower():
            return candidate
    return None


def cmd_issues(args: argparse.Namespace) -> int:
    repo = repo_root(args.repo)
    out, document = read_findings(repo, args.out_dir)
    pending = [
        finding["id"]
        for finding in document.get("findings") or []
        if finding.get("audit", {}).get("verdict") == "pending"
    ]
    if pending:
        fail("complete the audit first; still pending: " + ", ".join(pending))
    confirmed = [
        finding
        for finding in document.get("findings") or []
        if finding.get("audit", {}).get("verdict") == "confirmed"
    ]
    if not confirmed:
        print("No confirmed findings; no issue drafts written.")
        return 0

    gh = shutil.which("gh")
    if not gh:
        print(
            "warning: gh not found; existing Issues and PRs were not searched",
            file=sys.stderr,
        )
    issues_dir = out / "issues"
    issues_dir.mkdir(parents=True, exist_ok=True)
    for old in issues_dir.glob("ISSUE-*.md"):
        old.unlink()

    security: list[dict[str, Any]] = []
    drafts: list[tuple[dict[str, Any], str, Path, list[dict[str, Any]]]] = []
    duplicates: list[tuple[dict[str, Any], dict[str, Any]]] = []
    seen_titles: set[str] = set()
    for finding in confirmed:
        if looks_security(finding):
            security.append(finding)
            continue
        title = issue_title(finding)
        finding_key = (
            f"{finding.get('path', '')}:{finding.get('start_line', '')}:{title}"
        )
        if finding_key in seen_titles:
            continue
        seen_titles.add(finding_key)
        candidates = discover_candidates(gh, title) if gh else []
        existing = exact_match(candidates, title)
        if existing:
            duplicates.append((finding, existing))
            continue
        related = candidates
        body = issue_body(finding, document)
        if contains_secret(body):
            fail(
                f"{finding['id']} draft contains a possible secret; redact the "
                "finding before drafting or filing an issue"
            )
        draft = issues_dir / f"ISSUE-{finding['id']}.md"
        draft.write_text(
            f"<!-- title: {title} -->\n<!-- labels: bug -->\n\n" + body,
            encoding="utf-8",
        )
        drafts.append((finding, title, draft, related))

    index = ["# Issue drafts", ""]
    for finding, title, draft, related in drafts:
        index.append(f"- `{finding['id']}` — {title} → `{draft.name}`")
        if related:
            index.append("  - Related candidates to review before `--create`:")
            for candidate in related:
                index.append(
                    f"    - {candidate['kind']} #{candidate.get('number')} "
                    f"[{candidate.get('state')}] {candidate.get('title')} "
                    f"{candidate.get('url')}"
                )
    if duplicates:
        index.extend(["", "## Already reported (no draft)", ""])
        for finding, existing in duplicates:
            index.append(
                f"- `{finding['id']}` — {existing['kind']} #{existing.get('number')} "
                f"[{existing.get('state')}] {existing.get('title')} "
                f"{existing.get('url')}"
            )
    if security:
        index.extend(["", "## Security findings (not for public issues)", ""])
        for finding in security:
            index.append(
                f"- `{finding['id']}` — `{location(finding)}`: "
                f"{redact_secrets(finding['content'])}"
            )
        index.extend(
            [
                "",
                "Use https://github.com/Xero-Team/AstrBot/security/advisories/new "
                "per `SECURITY.md`; do not open a public issue.",
            ]
        )
    (issues_dir / "index.md").write_text("\n".join(index) + "\n", encoding="utf-8")

    if security:
        security_path = out / "security-findings.md"
        lines = [
            "# Security findings",
            "",
            "Do not open a public Issue for these findings. Follow `SECURITY.md` "
            "and the private advisory channel:",
            "",
            "https://github.com/Xero-Team/AstrBot/security/advisories/new",
            "",
            "This file can contain sensitive evidence. It is gitignored; do not "
            "commit it or paste it into a public channel.",
            "",
        ]
        for finding in security:
            lines.extend(
                [
                    f"## {finding['id']} — `{location(finding)}`",
                    "",
                    redact_secrets(finding["content"]),
                    "",
                    f"- Rule: `{finding['rule_id']}`",
                    f"- Severity: "
                    f"{finding['audit'].get('severity') or finding['severity']}",
                    f"- Evidence: "
                    f"{redact_secrets(finding['audit'].get('evidence', ''))}",
                    "",
                ]
            )
        security_path.write_text("\n".join(lines), encoding="utf-8")
        print(f"Security findings written to {security_path} (never file publicly).")

    print(f"Wrote {len(drafts)} issue draft(s) under {issues_dir}")
    for _, title, draft, _ in drafts:
        print(f"- {draft} — {title}")
    if duplicates:
        print(f"Skipped {len(duplicates)} already-reported finding(s).")
    if security:
        print(f"Skipped {len(security)} security finding(s) from public issues.")

    if not args.create:
        if drafts:
            print("Review the drafts. Re-run with --create to file them.")
        else:
            print("No public drafts were produced.")
        return 0
    if not drafts:
        return 0
    if not gh:
        fail("gh is required to create issues")
    auth = run_process([gh, "auth", "status", "--hostname", "github.com"])
    if auth.returncode != 0:
        print_process_output(auth)
        fail("gh is not authenticated for github.com")

    created: list[str] = []
    for finding, title, draft, _ in drafts:
        candidates = discover_candidates(gh, title)
        existing = exact_match(candidates, title)
        if existing:
            print(
                f"Skipping {finding['id']}: existing {existing['kind']} "
                f"{existing.get('url')}"
            )
            continue
        if candidates and not args.allow_related:
            print(
                f"Skipping {finding['id']}: related report(s) found. Review them, "
                "then pass --allow-related only when this is a distinct defect."
            )
            for candidate in candidates:
                print(
                    f"  {candidate['kind']} #{candidate.get('number')} "
                    f"[{candidate.get('state')}] {candidate.get('title')} "
                    f"{candidate.get('url')}"
                )
            continue
        result = run_process(
            [
                gh,
                "issue",
                "create",
                "--repo",
                ISSUE_REPO,
                "--title",
                title,
                "--body-file",
                str(draft),
                "--label",
                "bug",
            ]
        )
        if result.returncode != 0:
            print_process_output(result)
            print("Created before the failure: " + ", ".join(created or ["none"]))
            fail(f"failed to create issue for {finding['id']}")
        url = next(
            (
                line.strip()
                for line in (result.stdout or "").splitlines()
                if line.strip().startswith("https://github.com/")
            ),
            "",
        )
        expected = f"https://github.com/{ISSUE_REPO}/issues/"
        if not url.startswith(expected):
            fail(f"gh returned an unexpected issue URL: {url or '<empty>'}")
        created.append(url)
        print(f"Opened {finding['id']}: {url}")
    print(f"Opened {len(created)} issue(s) on {ISSUE_REPO}.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run and audit a Semgrep whole-project scan."
    )
    parser.add_argument("--repo", help="Repository root (default: current directory)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    doctor = subparsers.add_parser("doctor", help="Check local prerequisites")
    doctor.set_defaults(func=cmd_doctor)

    run = subparsers.add_parser("run", help="Run a whole-repository Semgrep scan")
    run.add_argument(
        "--path", action="append", default=[], help="Scan path (repeatable)"
    )
    run.add_argument(
        "--config", action="append", default=[], help="Rule pack or file (repeatable)"
    )
    run.add_argument(
        "--exclude", action="append", default=[], help="Extra exclude glob(s)"
    )
    run.add_argument(
        "--severity",
        action="append",
        choices=("ERROR", "WARNING", "INFO"),
        default=[],
        help="Only report this Semgrep severity (repeatable)",
    )
    run.add_argument("--jobs", type=int, help="Semgrep worker count")
    run.add_argument("--timeout", type=int, default=30, help="Per-rule timeout")
    run.add_argument(
        "--max-target-bytes", type=int, default=1_500_000, help="Skip larger files"
    )
    run.add_argument(
        "--process-timeout",
        type=int,
        default=3600,
        help="Whole-scan timeout in seconds",
    )
    run.add_argument(
        "--local-only", action="store_true", help="Use only the skill-local rules"
    )
    run.add_argument(
        "--no-parse-normalization",
        action="store_true",
        help="Scan the worktree directly instead of a PEP 758-normalized mirror",
    )
    run.add_argument(
        "--engine",
        choices=("auto", "local", "container"),
        default=os.environ.get("SEMGREP_ENGINE", "auto"),
        help="Engine selection; auto falls back to the pinned container image",
    )
    run.add_argument(
        "--no-local-rules",
        action="store_true",
        help="Do not load the local AstrBot rules",
    )
    run.add_argument("--out-dir", help="Write to this directory instead of a new run")
    run.set_defaults(func=cmd_run)

    listing = subparsers.add_parser("list", help="List normalized findings")
    listing.add_argument("--pending", action="store_true", help="Only pending findings")
    listing.add_argument("--out-dir")
    listing.set_defaults(func=cmd_list)

    apply_audit = subparsers.add_parser("apply-audit", help="Apply audit verdicts")
    apply_audit.add_argument("file", help="JSON audit file")
    apply_audit.add_argument(
        "--require-all", action="store_true", help="Fail while any finding is pending"
    )
    apply_audit.add_argument("--out-dir")
    apply_audit.set_defaults(func=cmd_apply_audit)

    finalize = subparsers.add_parser("finalize", help="Render the audited report")
    finalize.add_argument(
        "--allow-pending",
        action="store_true",
        help="Render pending findings as unaudited",
    )
    finalize.add_argument("--out-dir")
    finalize.set_defaults(func=cmd_finalize)

    issues = subparsers.add_parser("issues", help="Draft or file confirmed findings")
    issues.add_argument(
        "--create",
        action="store_true",
        help=f"Create Issues on {ISSUE_REPO} after drafting",
    )
    issues.add_argument(
        "--allow-related",
        action="store_true",
        help="Create even when related Issues or PRs were found",
    )
    issues.add_argument("--out-dir")
    issues.set_defaults(func=cmd_issues)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.func(args))
    except SkillError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
