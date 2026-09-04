import importlib.util
from pathlib import Path

import pytest

LEDGER_PATH = (
    Path(__file__).resolve().parents[2]
    / ".agents"
    / "skills"
    / "audit-product"
    / "scripts"
    / "audit_ledger.py"
)


def _load_ledger():
    spec = importlib.util.spec_from_file_location("audit_product_ledger", LEDGER_PATH)
    if spec is None or spec.loader is None:
        raise AssertionError(f"Failed to load {LEDGER_PATH}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _finding(**overrides: object) -> dict:
    payload: dict = {
        "schema_version": 1,
        "event_type": "finding",
        "recorded_at_utc": "2026-09-04T15:00:00Z",
        "revision": 2,
        "finding_id": "AUD-20260904-authz-001",
        "module_id": "authz",
        "title": "authorize fails open",
        "severity": "high",
        "kind": "security",
        "confidence": "likely",
        "location": "astrbot/core/auth/foo.py:12",
        "summary": "exception path returns allow",
        "status": "open",
    }
    payload.update(overrides)
    return payload


def test_confirmed_security_requires_boundary():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="boundary"):
        ledger.validate_event(_finding(confidence="confirmed"))


def test_confirmed_security_accepts_boundary_and_trace():
    ledger = _load_ledger()
    ledger.validate_event(
        _finding(
            confidence="confirmed",
            boundary="plugin tool to host FS",
            trace=["astrbot/core/auth/foo.py:12", "astrbot/core/auth/bar.py:40"],
        )
    )


def test_completeness_requires_contract_verdict():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="contract_verdict"):
        ledger.validate_event(
            _finding(
                kind="completeness",
                confidence="confirmed",
                severity="medium",
            )
        )


def test_completeness_accepts_contract_verdict():
    ledger = _load_ledger()
    ledger.validate_event(
        _finding(
            kind="completeness",
            confidence="confirmed",
            severity="medium",
            contract_verdict="absent",
        )
    )


def test_invalid_contract_verdict_rejected():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="contract_verdict"):
        ledger.validate_event(_finding(contract_verdict="kinda"))


def test_trace_entries_must_be_path_line():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="trace"):
        ledger.validate_event(_finding(trace=["no-colon"]))


def test_ux_smell_and_ai_ux_accepted():
    ledger = _load_ledger()
    ledger.validate_event(
        _finding(
            kind="completeness",
            confidence="confirmed",
            severity="medium",
            contract_verdict="partial",
            ux_smell="silent-errors",
            ai_ux="ai-action-consequences",
        )
    )


def test_invalid_ux_smell_rejected():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="ux_smell"):
        ledger.validate_event(_finding(ux_smell="ugly-buttons"))


def test_invalid_ai_ux_rejected():
    ledger = _load_ledger()
    with pytest.raises(ledger.LedgerError, match="ai_ux"):
        ledger.validate_event(_finding(ai_ux="make-it-fun"))


def test_add_finding_parser_exposes_new_flags():
    ledger = _load_ledger()
    parser = ledger.build_parser()
    args = parser.parse_args(
        [
            "add-finding",
            "--finding-id",
            "AUD-20260904-config-001",
            "--module",
            "config",
            "--title",
            "fallback secret",
            "--severity",
            "high",
            "--kind",
            "security",
            "--confidence",
            "confirmed",
            "--location",
            "astrbot/core/config/default.py:10",
            "--summary",
            "env fallback is a hardcoded key",
            "--boundary",
            "operator config to runtime secret",
            "--contract-verdict",
            "contradicted",
            "--trace",
            "astrbot/core/config/default.py:10",
            "astrbot/core/config/astrbot_config.py:80",
            "--ux-smell",
            "dead-end-states",
            "--ai-ux",
            "ai-transparency",
        ]
    )
    assert args.boundary == "operator config to runtime secret"
    assert args.contract_verdict == "contradicted"
    assert args.trace == [
        "astrbot/core/config/default.py:10",
        "astrbot/core/config/astrbot_config.py:80",
    ]
    assert args.ux_smell == "dead-end-states"
    assert args.ai_ux == "ai-transparency"
