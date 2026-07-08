def score_text(query: str, text: str) -> int:
    terms = {term.casefold() for term in query.split() if term.strip()}
    if not terms:
        return 0
    lowered = text.casefold()
    return sum(1 for term in terms if term in lowered)
