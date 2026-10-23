import pytest

from astrbot.core.knowledge_base.chunking.markdown import MarkdownChunker
from astrbot.core.knowledge_base.chunking.recursive import RecursiveCharacterChunker


@pytest.mark.asyncio
async def test_recursive_character_chunker_falls_back_to_character_chunks():
    chunker = RecursiveCharacterChunker(
        chunk_size=5,
        chunk_overlap=2,
        separators=[""],
    )

    chunks = await chunker.chunk("abcdefghij")

    assert chunks == ["abcde", "defgh", "ghij"]


def test_recursive_character_chunker_rejects_invalid_overlap():
    chunker = RecursiveCharacterChunker(chunk_size=5, chunk_overlap=2)

    with pytest.raises(ValueError, match="chunk_overlap must be less than chunk_size"):
        chunker._split_by_character("abcdef", chunk_size=5, overlap=5)


@pytest.mark.asyncio
async def test_markdown_chunker_skips_headings_inside_fenced_code_blocks():
    chunker = MarkdownChunker(chunk_size=80)
    text = """# Title

Intro

```python
# Not a heading
```

## Section
Body
"""

    chunks = await chunker.chunk(text)

    assert len(chunks) == 2
    assert "# Not a heading" in chunks[0]
    assert "Title" in chunks[1]
    assert "## Section" in chunks[1]


@pytest.mark.asyncio
async def test_recursive_chunker_never_exceeds_chunk_size_with_overlap():
    from astrbot.core.knowledge_base.chunking.recursive import (
        RecursiveCharacterChunker,
    )

    chunks = await RecursiveCharacterChunker().chunk(
        "a" * 25 + " " + "b" * 25,
        chunk_size=10,
        chunk_overlap=9,
    )

    assert all(len(chunk) <= 10 for chunk in chunks)


def test_overlap_state_never_exceeds_chunk_size():
    from astrbot.core.knowledge_base.chunking.recursive import (
        RecursiveCharacterChunker,
    )

    chunker = RecursiveCharacterChunker(chunk_size=10, chunk_overlap=9)
    parts, length = chunker._build_overlap_state(
        combined_text="a" * 7,
        split="b" * 6,
        overlap=9,
        chunk_size=10,
    )

    assert length <= 10
    assert len("".join(parts)) <= 10
