import io

from astrbot.core.log import _SafeConsoleStream


class _GbKTextStream:
    def __init__(self) -> None:
        self.buffer = io.BytesIO()
        self.encoding = "gbk"

    def write(self, message: str) -> None:
        self.buffer.write(message.encode(self.encoding))

    def flush(self) -> None:
        return

    def isatty(self) -> bool:
        return False


def test_safe_console_stream_falls_back_when_stream_encoding_rejects_unicode():
    stream = _GbKTextStream()
    sink = _SafeConsoleStream(stream)

    sink.write("AstrBot ✨ ready\n")

    assert stream.buffer.getvalue().decode("gbk") == "AstrBot \\u2728 ready\n"
