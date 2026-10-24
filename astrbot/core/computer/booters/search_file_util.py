_MAX_SEARCH_TOTAL_CHARS = 200_000
_MAX_SEARCH_LINE_COLUMNS = 1000


def _truncate_long_lines(text: str) -> str:
    output_lines: list[str] = []
    total_chars = 0
    for line in text.splitlines(keepends=True):
        line_ending = ""
        line_body = line
        if line.endswith("\r\n"):
            line_body = line[:-2]
            line_ending = "\r\n"
        elif line.endswith("\n") or line.endswith("\r"):
            line_body = line[:-1]
            line_ending = line[-1]

        if len(line_body) > _MAX_SEARCH_LINE_COLUMNS:
            line_body = line_body[:_MAX_SEARCH_LINE_COLUMNS]

        rendered = f"{line_body}{line_ending}"
        if total_chars + len(rendered) > _MAX_SEARCH_TOTAL_CHARS:
            output_lines.append("\n[output truncated]\n")
            break
        output_lines.append(rendered)
        total_chars += len(rendered)
    return "".join(output_lines)
