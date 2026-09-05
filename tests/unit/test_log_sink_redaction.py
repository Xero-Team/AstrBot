"""Sink-level log redaction for console, file, queue, and Trace payloads."""

from __future__ import annotations

import io
import json
import logging
import sys
from collections.abc import Iterator
from contextlib import contextmanager

from loguru import logger as raw_loguru

from astrbot.core.log import (
    LogBroker,
    LogManager,
    LogQueueHandler,
    _loguru,
    _LoguruInterceptHandler,
    sanitize_log_payload,
    sanitize_log_record,
)

MARKER = "sink-redaction-marker-32"
AUTH_MARKER = "sink-redaction-auth-32"
URL = "https://sink-redaction.example.test/private"
ABS_PATH = "/srv/astrbot/sink-redaction/marker.json"
DIAGNOSE_PROBE = "diagnose-local-should-not-appear-32"
SENSITIVE_MESSAGE = f"api_key={MARKER} Bearer {AUTH_MARKER} {URL} {ABS_PATH}"


def _assert_redacted(text: str) -> None:
    assert MARKER not in text
    assert AUTH_MARKER not in text
    assert "sink-redaction.example.test" not in text
    assert ABS_PATH not in text
    assert DIAGNOSE_PROBE not in text


def _assert_no_diagnose_dump(text: str) -> None:
    assert DIAGNOSE_PROBE not in text
    assert f"diagnose_local_probe = {DIAGNOSE_PROBE!r}" not in text


def _raise_sensitive() -> None:
    diagnose_local_probe = DIAGNOSE_PROBE
    if not diagnose_local_probe:
        raise AssertionError("diagnose probe missing")
    raise ValueError(SENSITIVE_MESSAGE)


def _record_from_exc(
    msg: str,
    exc_info: tuple[type[BaseException], BaseException, object] | None = None,
) -> logging.LogRecord:
    return logging.LogRecord(
        "astrbot",
        logging.ERROR,
        __file__,
        1,
        msg,
        (),
        exc_info,
    )


@contextmanager
def _capture_loguru(*, diagnose: bool = True) -> Iterator[io.StringIO]:
    buf = io.StringIO()
    sink_id = _loguru.add(
        buf,
        level="DEBUG",
        colorize=False,
        diagnose=diagnose,
        backtrace=True,
        format="{message}",
        catch=False,
    )
    try:
        yield buf
    finally:
        _loguru.remove(sink_id)


def test_sanitize_log_record_redacts_message_and_is_idempotent() -> None:
    record = _record_from_exc(SENSITIVE_MESSAGE)
    first = sanitize_log_record(record)
    assert first is record
    _assert_redacted(record.getMessage())
    assert record.args == ()
    assert record.astrbot_sanitized is True
    redacted = record.msg
    second = sanitize_log_record(record)
    assert second.msg == redacted
    assert "[REDACTED]" in second.msg


def test_sanitize_log_record_overwrites_raw_exc_text() -> None:
    try:
        _raise_sensitive()
    except ValueError:
        record = _record_from_exc("failed", sys.exc_info())
    record.exc_text = f"LEAKED {SENSITIVE_MESSAGE}"
    sanitize_log_record(record)
    assert record.exc_info is None
    assert record.exc_text is not None
    assert "LEAKED" not in record.exc_text
    _assert_redacted(record.exc_text)
    _assert_no_diagnose_dump(record.exc_text)
    preserved = record.exc_text
    sanitize_log_record(record)
    assert record.exc_text == preserved


def test_sanitize_log_record_redacts_exc_text_without_exc_info() -> None:
    record = _record_from_exc("failed")
    record.exc_text = f"LEAKED {SENSITIVE_MESSAGE}"
    sanitize_log_record(record)
    assert record.exc_info is None
    assert record.exc_text is not None
    _assert_redacted(record.exc_text)
    assert "api_key=[REDACTED]" in record.exc_text


def test_exc_text_without_exc_info_is_redacted_on_console() -> None:
    handler = _LoguruInterceptHandler()
    record = _record_from_exc("failed")
    record.exc_text = f"LEAKED {SENSITIVE_MESSAGE}"
    with _capture_loguru() as buf:
        handler.emit(record)
    text = buf.getvalue()
    assert "failed" in text
    _assert_redacted(text)
    assert "api_key=[REDACTED]" in text


def test_sanitize_log_record_redacts_stack_info() -> None:
    record = _record_from_exc("stack")
    record.stack_info = f"Stack (most recent call last):\n{SENSITIVE_MESSAGE}"
    sanitize_log_record(record)
    assert record.stack_info is not None
    _assert_redacted(record.stack_info)


def test_sanitize_log_record_redacts_exception_chain() -> None:
    try:
        try:
            raise ValueError(f"api_key={MARKER}")
        except ValueError as exc:
            raise RuntimeError(URL) from exc
    except RuntimeError:
        record = _record_from_exc("chained", sys.exc_info())
    sanitize_log_record(record)
    assert record.exc_text is not None
    _assert_redacted(record.exc_text)
    assert "direct cause of the following exception" in record.exc_text


def test_sanitize_log_record_redacts_exception_group() -> None:
    try:
        raise ExceptionGroup(
            "group",
            [ValueError(f"api_key={MARKER}"), RuntimeError(URL)],
        )
    except ExceptionGroup:
        record = _record_from_exc("group", sys.exc_info())
    sanitize_log_record(record)
    assert record.exc_text is not None
    _assert_redacted(record.exc_text)
    assert "ExceptionGroup" in record.exc_text


def test_sanitize_log_record_handles_unprintable_message_and_exception() -> None:
    record = _record_from_exc("%s %s")
    record.args = ("only-one",)
    sanitize_log_record(record)
    assert record.msg == "<unprintable log message>"
    assert record.args == ()

    broken = _record_from_exc("broken")
    broken.exc_info = object()
    sanitize_log_record(broken)
    assert broken.exc_text == "<unprintable exception>"
    assert broken.exc_info is None


def test_queue_formatter_does_not_duplicate_traceback() -> None:
    try:
        _raise_sensitive()
    except ValueError:
        record = _record_from_exc("failed", sys.exc_info())
    sanitize_log_record(record)
    formatted = logging.Formatter("%(message)s").format(record)
    assert formatted.count("Traceback (most recent call last)") == 1
    assert formatted.startswith("failed")
    _assert_redacted(formatted)


def test_sanitize_log_payload_copies_and_keeps_non_strings() -> None:
    original = {
        "event_id": "keep-me",
        "count": 3,
        "ok": True,
        "nested": None,
        "items": ["api_key=" + MARKER, 2],
        "pair": (URL, False),
        "fields": {"probe": f"api_key={MARKER}"},
    }
    copied = sanitize_log_payload(original)
    assert copied is not original
    assert original["items"][0] == f"api_key={MARKER}"
    assert original["fields"]["probe"] == f"api_key={MARKER}"
    assert copied["event_id"] == "keep-me"
    assert copied["count"] == 3
    assert copied["ok"] is True
    assert copied["nested"] is None
    assert copied["items"][1] == 2
    assert copied["pair"][1] is False
    _assert_redacted(copied["items"][0])
    _assert_redacted(copied["fields"]["probe"])
    _assert_redacted(copied["pair"][0])


def test_log_broker_publish_does_not_mutate_caller_payload() -> None:
    payload = {
        "event_id": "keep-me",
        "data": f"api_key={MARKER}",
        "category": "system",
    }
    broker = LogBroker()
    subscriber = broker.register()
    broker.publish(payload)
    assert payload["data"] == f"api_key={MARKER}"
    cached = broker.log_cache[-1]
    queued = subscriber.get_nowait()
    assert cached is not payload
    assert queued is cached
    assert cached["event_id"] == "keep-me"
    assert cached["category"] == "system"
    _assert_redacted(cached["data"])


def test_astrbot_logger_error_redacts_console_output() -> None:
    logger = LogManager.GetLogger("astrbot")
    with _capture_loguru() as buf:
        logger.error(SENSITIVE_MESSAGE)
        try:
            _raise_sensitive()
        except ValueError:
            logger.exception("console exception")
        logger.error("explicit exc", exc_info=ValueError(SENSITIVE_MESSAGE))
        logger.error("payload {not_a_field} api_key=%s", MARKER)
        logger.error(SENSITIVE_MESSAGE, stack_info=True)
    text = buf.getvalue()
    _assert_redacted(text)
    _assert_no_diagnose_dump(text)
    assert "console exception" in text
    assert "not_a_field" in text
    assert "Traceback (most recent call last)" in text
    assert "Stack (most recent call last)" in text


def test_native_loguru_logger_redacts_file_sink(tmp_path) -> None:
    LogManager.GetLogger("astrbot")
    previous_file = LogManager._file_sink_id
    log_path = tmp_path / "native-loguru.log"
    try:
        LogManager._file_sink_id = LogManager._add_file_sink(
            file_path=str(log_path),
            level=logging.DEBUG,
            max_mb=None,
            backup_count=0,
            trace=False,
        )
        raw_loguru.bind(
            plugin_tag="[Core]",
            short_levelname="ERRO",
            astrbot_version_tag="",
            source_file="test.log_sink",
            source_line=1,
            is_trace=False,
        ).opt(exception=False).error(SENSITIVE_MESSAGE)
        LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = None
        text = log_path.read_text(encoding="utf-8")
    finally:
        if LogManager._file_sink_id not in {None, previous_file}:
            LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = previous_file
    _assert_redacted(text)
    assert "api_key=[REDACTED]" in text


def test_file_sink_redacts_after_enqueue_flush(tmp_path) -> None:
    logger = LogManager.GetLogger("astrbot")
    previous_file = LogManager._file_sink_id
    log_path = tmp_path / "astrbot.log"
    try:
        LogManager._file_sink_id = LogManager._add_file_sink(
            file_path=str(log_path),
            level=logging.DEBUG,
            max_mb=None,
            backup_count=0,
            trace=False,
        )
        logger.error(SENSITIVE_MESSAGE)
        try:
            _raise_sensitive()
        except ValueError:
            logger.exception("file exception")
        LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = None
        text = log_path.read_text(encoding="utf-8")
    finally:
        if LogManager._file_sink_id not in {None, previous_file}:
            LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = previous_file
    _assert_redacted(text)
    _assert_no_diagnose_dump(text)
    assert "file exception" in text


def test_third_party_logger_redacts_console_and_file(tmp_path) -> None:
    LogManager.GetLogger("astrbot")
    previous_file = LogManager._file_sink_id
    log_path = tmp_path / "third-party.log"
    try:
        LogManager._file_sink_id = LogManager._add_file_sink(
            file_path=str(log_path),
            level=logging.DEBUG,
            max_mb=None,
            backup_count=0,
            trace=False,
        )
        with _capture_loguru() as buf:
            logging.getLogger("astrbot_test_third_party_lib").error(SENSITIVE_MESSAGE)
        LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = None
        file_text = log_path.read_text(encoding="utf-8")
    finally:
        if LogManager._file_sink_id not in {None, previous_file}:
            LogManager._remove_sink(LogManager._file_sink_id)
        LogManager._file_sink_id = previous_file
    _assert_redacted(buf.getvalue())
    _assert_redacted(file_text)


def test_preexisting_root_stream_handler_sees_logger_filter() -> None:
    LogManager.GetLogger("astrbot")
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    root = logging.getLogger()
    root.addHandler(handler)
    try:
        logging.getLogger().error(SENSITIVE_MESSAGE)
        text = stream.getvalue()
    finally:
        root.removeHandler(handler)
        handler.close()
    _assert_redacted(text)
    assert "api_key=[REDACTED]" in text


def test_log_queue_handler_emits_single_redacted_stack() -> None:
    broker = LogBroker()
    handler = LogQueueHandler(broker)
    handler.setFormatter(logging.Formatter("%(message)s"))
    try:
        _raise_sensitive()
    except ValueError:
        record = _record_from_exc("queued", sys.exc_info())
    handler.emit(record)
    entry = broker.log_cache[-1]
    _assert_redacted(entry["data"])
    assert entry["data"].count("Traceback (most recent call last)") == 1


def test_trace_span_record_redacts_nested_fields(monkeypatch) -> None:
    import astrbot.core.utils.trace as trace_mod

    original_fields = {
        "nested": {
            "url": URL,
            "probe": f"api_key={MARKER}",
        }
    }
    broker = LogBroker()
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    trace_logger = logging.getLogger("astrbot.trace")
    previous_level = trace_logger.level
    previous_propagate = trace_logger.propagate
    monkeypatch.setattr(trace_mod, "_config", {"trace_enable": True})
    monkeypatch.setattr(trace_mod, "_trace_logger", trace_logger)
    monkeypatch.setattr(trace_mod, "_cached_log_broker", broker)
    LogManager._ensure_logger_sanitize_filter(trace_logger)
    trace_logger.addHandler(handler)
    trace_logger.setLevel(logging.INFO)
    trace_logger.propagate = False
    try:
        trace_mod.TraceSpan("sink-redaction").record("call", extra=original_fields)
        assert original_fields["nested"]["url"] == URL
        assert original_fields["nested"]["probe"] == f"api_key={MARKER}"
        entry = broker.log_cache[-1]
        dumped = stream.getvalue()
        parsed = json.loads(dumped.strip().splitlines()[-1])
    finally:
        trace_logger.removeHandler(handler)
        handler.close()
        trace_logger.setLevel(previous_level)
        trace_logger.propagate = previous_propagate
    _assert_redacted(json.dumps(entry))
    _assert_redacted(dumped)
    assert parsed["fields"]["extra"]["nested"]["url"] == "[REDACTED_URL]"
    assert parsed["fields"]["extra"]["nested"]["probe"] == "api_key=[REDACTED]"
    assert entry["fields"]["extra"]["nested"]["url"] == "[REDACTED_URL]"


def test_configure_logger_replacement_console_sink_disables_diagnose() -> None:
    logger = LogManager.GetLogger("astrbot")
    previous_console = LogManager._console_sink_id
    previous_configured = LogManager._configured
    previous_level = logger.level
    previous_root_level = logging.getLogger().level
    try:
        LogManager.configure_logger(logger, {"log_level": "DEBUG"})
        sink_id = LogManager._console_sink_id
        assert sink_id is not None
        formatter = _loguru._core.handlers[sink_id]._exception_formatter
        assert formatter._diagnose is False
        assert formatter._backtrace is False
        with _capture_loguru(diagnose=True) as buf:
            try:
                _raise_sensitive()
            except ValueError:
                logger.exception("replaced sink")
        text = buf.getvalue()
        _assert_redacted(text)
        _assert_no_diagnose_dump(text)
    finally:
        if LogManager._console_sink_id not in {None, previous_console}:
            LogManager._remove_sink(LogManager._console_sink_id)
        if previous_console is None or previous_console not in _loguru._core.handlers:
            LogManager._configured = False
            LogManager._console_sink_id = None
            LogManager._setup_loguru()
        else:
            LogManager._console_sink_id = previous_console
            LogManager._configured = previous_configured
        logger.setLevel(previous_level)
        logging.getLogger().setLevel(previous_root_level)
