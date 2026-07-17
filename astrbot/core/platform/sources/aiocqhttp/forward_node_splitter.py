"""Utilities for bounded OneBot forward-message text nodes."""

import re


def split_long_text_node(
    text: str,
    max_length: int,
    boundary_pattern: str,
) -> list[str]:
    """Split text at natural boundaries, falling back to a hard length limit."""
    if max_length <= 0:
        raise ValueError("max_length must be positive")
    if len(text) <= max_length:
        return [text]

    boundary_re = re.compile(boundary_pattern)
    chunks: list[str] = []
    remaining = text
    while len(remaining) > max_length:
        candidate_end = 0
        for match in boundary_re.finditer(remaining):
            if match.end() > max_length:
                break
            candidate_end = match.end()
        split_at = candidate_end or max_length
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:]
    if remaining:
        chunks.append(remaining)
    return chunks
