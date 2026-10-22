"""Number parsing shared by the claim extractors: digits, magnitudes and English number words.

Numerals are read in English and French formats: ``68,400`` and ``12.5``, and ``279,99`` (decimal
comma) and ``1 299,99`` (digit groups split by a space).
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation

__all__ = [
    "NUMBER_WORDS_RE",
    "NUMERAL_RE",
    "canonical_decimal",
    "parse_magnitude",
    "parse_number_words",
    "parse_numeral",
]

_UNITS = {
    "zero": 0,
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
    "thirteen": 13,
    "fourteen": 14,
    "fifteen": 15,
    "sixteen": 16,
    "seventeen": 17,
    "eighteen": 18,
    "nineteen": 19,
    "twenty": 20,
    "thirty": 30,
    "forty": 40,
    "fifty": 50,
    "sixty": 60,
    "seventy": 70,
    "eighty": 80,
    "ninety": 90,
}
_SCALES = {"hundred": 100, "thousand": 1_000, "million": 1_000_000}

_WORD = "(?:" + "|".join(sorted([*_UNITS, *_SCALES], key=len, reverse=True)) + ")"
#: One or more English number words ("fifty-two", "one hundred and twenty").
NUMBER_WORDS_RE = rf"\b{_WORD}(?:(?:[\s-]+(?:and[\s-]+)?){_WORD})*\b"

# A decimal comma: 1 or 2 digits and no digit after them ("279,99", "1,2 kg"). Not a list of
# numbers ("2,4,6"), nor a chemical locant: primed, bracketed or followed by a dash (any kind)
# and a letter ("3,3'-", "[1,2,4]triazolo", "2,2(bis", "1,3,5,-triazine", "1,3-butadiene").
_DECIMAL_GUARD = r"(?!\d|,\d|,-|['’]|[\]()]|[-‐–—]\s?[^\W\d_])"
_DECIMAL_COMMA = rf",\d{{1,2}}{_DECIMAL_GUARD}"
# Nor a number right after "[" or a comma ("[1,4]", the "2,4" of "1,2,4").
_DECIMAL_START = r"(?<![\[,\d])"
# A lone "0" before a comma and three digits is a decimal too ("0,965 kWh"): English writes no
# thousands group after "0". In a list ("100,0,100,0") it is neither a decimal nor thousands.
#: A numeral with optional thousands separators and decimals ("68,400", "12.5", "68400"); in
#: French formats a decimal comma ("279,99") and digit groups split by a no-break or narrow
#: no-break space ("1 299"), or by a plain space before a decimal comma ("1 299,99"); and "0,965".
NUMERAL_RE = (
    rf"(?:{_DECIMAL_START}0,\d{{3}}{_DECIMAL_GUARD}"
    r"|(?!0,\d{3}(?!,\d{3}))\d{1,3}(?:,\d{3})+(?:\.\d+)?"
    rf"|(?<!\d)\d{{1,3}}(?:[\u00a0\u202f]\d{{3}})+(?!\d)(?:{_DECIMAL_COMMA}|\.\d+)?"
    rf"|{_DECIMAL_START}\d{{1,3}}(?: \d{{3}})+{_DECIMAL_COMMA}"
    rf"|{_DECIMAL_START}\d+{_DECIMAL_COMMA}"
    r"|\d+(?:\.\d+)?)"
)

_GROUP_SPACES = str.maketrans("", "", " \u00a0\u202f")

_MAGNITUDES = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "mn": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "bn": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
}


def canonical_decimal(value: Decimal) -> str:
    """Render a decimal without exponent or trailing zeros: 68400, 12.5, 0.25 (any magnitude)."""
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def parse_numeral(text: str) -> Decimal | None:
    """Parse ``68,400`` / ``12.5`` / ``279,99`` / ``1 299,99``; ``None`` when not a numeral."""
    text = text.translate(_GROUP_SPACES)
    decimal = re.fullmatch(r"\d+,\d{1,2}|0,\d{3}", text)
    text = text.replace(",", ".") if decimal else text.replace(",", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_magnitude(word: str | None) -> Decimal:
    """Multiplier for ``k`` / ``m`` / ``million`` …; 1 when absent or unknown."""
    if not word:
        return Decimal(1)
    return _MAGNITUDES.get(word.lower(), Decimal(1))


def parse_number_words(text: str) -> int | None:
    """Parse number words ("fifty-two", "one hundred and five"); ``None`` if any word is not one."""
    words = [w for w in re.split(r"[\s-]+", text.lower()) if w and w != "and"]
    if not words:
        return None
    total = 0
    current = 0
    for word in words:
        if word in _UNITS:
            current += _UNITS[word]
        elif word == "hundred":
            current = max(current, 1) * 100
        elif word in _SCALES:
            total += max(current, 1) * _SCALES[word]
            current = 0
        else:
            return None
    return total + current
