def text_check(
    text: str,
    must_contain: list[str],
    must_not_contain: list[str],
) -> bool:
    lower = text.lower()
    if any(word.lower() in lower for word in must_not_contain):
        return False
    if must_contain and not any(word.lower() in lower for word in must_contain):
        return False
    return True
