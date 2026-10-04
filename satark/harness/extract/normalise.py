"""Text normalisation before any identifier pattern runs (LLD §8.1 step, CONTRACTS §4).

Pure function, no case/config needed: Unicode NFKC, zero-width removal, Indic digits -> ASCII,
Devanagari nukta/chandrabindu folding, whitespace collapse (newlines kept: sms.header anchors
on line starts), a 4,000 char cap.
"""

from __future__ import annotations

import re
import unicodedata

MAX_CHARS = 4_000

_ZERO_WIDTH = str.maketrans({cp: None for cp in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)})

# Hindi is written both with and without the nukta (रोज़ाना/रोजाना, मुनाफ़ा/मुनाफा): NFKC composes
# a decomposed base+nukta sequence into one precomposed codepoint (e.g. ज+़ -> ज़), but that is
# a different letter from the nukta-less base, not an encoding ambiguity, so NFKC alone cannot
# fold them together. Decomposing first (NFD) and dropping U+093C unifies both spellings onto
# the nukta-less base consonant before any pattern runs. Chandrabindu/anusvara (हँ/हं) is a
# similar free-variation pair, folded the other way (chandrabindu -> anusvara) by a direct map.
_NUKTA = "़"
_OPTIONAL_NUKTA = _NUKTA + "?"  # the pattern-authoring convention for "nukta optional"
_CHANDRABINDU_TO_ANUSVARA = str.maketrans({0x0901: 0x0902})

# Each block's 10 code points are that script's digits 0-9, in order (Unicode Common properties).
_DIGIT_BLOCK_STARTS = (
    0x0966,  # Devanagari
    0x09E6,  # Bengali
    0x0A66,  # Gurmukhi
    0x0AE6,  # Gujarati
    0x0B66,  # Odia
    0x0BE6,  # Tamil
    0x0C66,  # Telugu
    0x0CE6,  # Kannada
    0x0D66,  # Malayalam
)
_INDIC_DIGITS = str.maketrans(
    {start + i: chr(ord("0") + i) for start in _DIGIT_BLOCK_STARTS for i in range(10)}
)

_SPACES_TABS = re.compile(r"[ \t]+")


def normalise_text(text: str) -> str:
    """NFKC-normalise, strip zero-width chars and the Devanagari nukta (folding spelling
    variants like रोज़ाना/रोजाना onto one form), map Indic digits to ASCII, collapse spaces/tabs
    (newlines kept), cap at MAX_CHARS."""
    s = unicodedata.normalize("NFD", text or "")  # split a precomposed nukta letter (ज़) into ज + ़
    s = s.replace(_NUKTA, "")
    s = unicodedata.normalize("NFKC", s)
    s = s.translate(_ZERO_WIDTH)
    s = s.translate(_INDIC_DIGITS)
    s = s.translate(_CHANDRABINDU_TO_ANUSVARA)
    s = _LETTER_SPACED.sub(lambda m: m.group(0).replace(" ", ""), s)  # "R B I  N O T I C E" -> "RBI NOTICE"
    s = _SPACES_TABS.sub(" ", s)
    return s[:MAX_CHARS]


# Scam texts space out words letter by letter to slip past filters ("C O N G R A T S"). Three or more
# single Latin letters separated by single spaces are one word (runs before spaces are collapsed, so a
# wider gap still separates two spaced-out words).
_LETTER_SPACED = re.compile(r"(?<![A-Za-z])(?:[A-Za-z] ){2,}[A-Za-z](?![A-Za-z])")


def fold_pattern(p: str) -> str:
    """Apply the same Devanagari nukta/chandrabindu folding `normalise_text` applies to input
    text, to a *pattern* string, so a literal Devanagari pattern still matches folded text.
    Use this on every pattern/context/role_hint before compiling it (CONTRACTS §4); other
    engineers' lexicons (checkers, FAQ matching) should call this too.

    A pattern may spell an optional nukta explicitly as "़?" (the nukta character followed by
    a literal regex "?"), e.g. 'मुनाफ़?ा' or 'सिर्फ़?\\s*आज' - matching "मुनाफ़ा" or "मुनाफा". That
    two-character sequence must be dropped as a unit: stripping just the nukta character would
    leave a bare "?" behind, which then makes the *consonant* optional instead of the nukta
    ('फ़?' -> 'फ?' silently changes what the pattern means, not what we want)."""
    s = unicodedata.normalize("NFD", p)
    s = s.replace(_OPTIONAL_NUKTA, "")
    s = s.replace(_NUKTA, "")
    s = unicodedata.normalize("NFKC", s)
    return s.translate(_CHANDRABINDU_TO_ANUSVARA)
