from __future__ import annotations

import re


def _context(text: str | None) -> str:
    return text.casefold() if isinstance(text, str) else ""


def infer_surface_pattern(
    *,
    category: str,
    surface: str,
    text: str | None = None,
    source_category: str | None = None,
) -> str | None:
    """Infer a coverage pattern only from mechanically visible evidence."""
    category_name = category.casefold()
    value = surface.strip()
    context = _context(text)
    source = (source_category or "").casefold()

    if category_name == "decimal":
        if re.fullmatch(r"-?\.\d+", value):
            return "leading_decimal"
        if "," in value:
            return "grouped_decimal"
        if value.startswith("-"):
            return "negative_decimal"
        if re.match(r"0\d*\.\d+", value):
            return "leading_zero"
        return "plain_decimal"

    if category_name == "date":
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            return "iso_date"
        if re.search(r"[A-Za-z]", value):
            return "month_name_date"
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{2,4})", value)
        if match and int(match.group(1)) <= 12 and int(match.group(2)) <= 12:
            return "ambiguous_numeric_date"
        if "/" in value:
            return "slash_date"
        return None

    if category_name == "time":
        if value in {"00:00", "00:00:00", "12:00 AM", "12:00:00 AM"}:
            return "midnight"
        if re.search(r"(?:AM|PM)$", value, re.IGNORECASE):
            return "time_12h"
        if re.match(r"0\d:", value):
            return "leading_zero_time"
        if re.fullmatch(r"\d{1,2}:\d{2}(?::\d{2})?", value):
            return "time_24h"
        return None

    if category_name == "fraction":
        if re.fullmatch(r"\d+/\d+", value):
            fraction_words = ("fraction", "numerator", "denominator", "quarter", "half")
            return (
                "numeric_fraction"
                if any(word in context for word in fraction_words)
                else "fraction_vs_slash"
            )
        return None

    if category_name == "identifier":
        if re.fullmatch(r"[A-Za-z]+\d+", value) or re.fullmatch(r"\d+[A-Za-z]+", value):
            return "letters_digits"
        if re.search(r"[-_:.]", value):
            return "mixed_identifier"
        if re.search(r"\d", value) and re.search(r"[A-Za-z]", value):
            return "letters_digits"
        if re.fullmatch(r"[A-Za-z]+", value):
            return "identifier_vs_word"
        return "mixed_identifier"

    if category_name == "score_or_range":
        if re.search(r"(?:\d+\s*-\s*){2}\d+", context):
            return "countdown"
        if re.search(r"\b(range|from|between|through|to)\b", context):
            return "numeric_range"
        return "score"

    if category_name == "math_expression":
        if "^" in value:
            return "power"
        if "/" in value:
            return "division"
        if re.search(r"[A-Za-z]\d+", value) or "_" in value:
            return "subscript"
        if "-" in value:
            return "subtraction"
        return None

    if category_name == "version":
        if "-" in value:
            return "prerelease_version"
        if len(value.lstrip("v").split(".")) >= 3:
            return "semantic_version"
        return "simple_version"

    if category_name == "ip_address":
        return "ipv4" if re.fullmatch(r"\d{1,3}(?:\.\d{1,3}){3}", value) else None

    if category_name == "url_or_email":
        if re.fullmatch(r"https?://\S+", value, re.IGNORECASE):
            return "url"
        if re.fullmatch(r"[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}", value):
            return "email"
        return None

    if category_name == "acronym":
        if re.fullmatch(r"[A-Z]{2,}s", value):
            return "plural_acronym"
        if re.fullmatch(r"[A-Z]{2,}", value):
            return "initialism"
        if re.fullmatch(r"[A-Za-z]{2,}", value):
            return "word_like_acronym"
        return None

    if source == category_name and category_name in {"date", "time", "version"}:
        return None
    return None
