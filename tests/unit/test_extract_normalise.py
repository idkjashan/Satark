"""normalise_text: NFKC, zero-width removal, Indic digits -> ASCII, whitespace, 4,000 cap
(CONTRACTS §4, LLD §8.1)."""

from __future__ import annotations

import re

from satark.harness.extract.normalise import MAX_CHARS, fold_pattern, normalise_text


def test_indic_digits_mapped_to_ascii():
    assert normalise_text("०१२३४५६७८९") == "0123456789"  # Devanagari
    assert normalise_text("৯৮৭৬৫") == "98765"  # Bengali
    assert normalise_text("੧੨੩") == "123"  # Gurmukhi
    assert normalise_text("૧૨૩") == "123"  # Gujarati
    assert normalise_text("୧୨୩") == "123"  # Odia
    assert normalise_text("௧௨௩") == "123"  # Tamil
    assert normalise_text("౧౨౩") == "123"  # Telugu
    assert normalise_text("೧೨೩") == "123"  # Kannada
    assert normalise_text("൧൨൩") == "123"  # Malayalam


def test_zero_width_chars_removed():
    text = "rajesh​.vip‌@‍okaxis⁠﻿"
    assert normalise_text(text) == "rajesh.vip@okaxis"


def test_nfkc_normalises_compatibility_forms():
    # full-width digit and ligature-ish compatibility forms fold to their plain ASCII form
    assert "1" in normalise_text("１")  # fullwidth "1"


def test_spaces_and_tabs_collapsed_newlines_kept():
    text = "line one\t\t  spaced   out\nSECOND-LINE\n\nthird"
    out = normalise_text(text)
    assert "\n" in out
    assert out.count("\n") == 3
    assert "  " not in out
    assert "line one spaced out" in out


def test_caps_at_4000_chars():
    out = normalise_text("a" * 10_000)
    assert len(out) == MAX_CHARS


def test_empty_and_none_safe():
    assert normalise_text("") == ""
    assert normalise_text(None) == ""  # type: ignore[arg-type]


def test_idempotent():
    text = "Pay ₹१,००,००० to rajesh@okaxis​ now"
    once = normalise_text(text)
    twice = normalise_text(once)
    assert once == twice


def test_nukta_spelling_variants_fold_to_the_same_text():
    """Hindi is written both with and without the nukta: रोज़ाना/रोजाना, मुनाफ़ा/मुनाफा must
    normalise identically so a pattern written in either spelling still matches."""
    assert normalise_text("रोज़ाना") == normalise_text("रोजाना")
    assert normalise_text("मुनाफ़ा") == normalise_text("मुनाफा")
    assert normalise_text("सिर्फ़ आज") == normalise_text("सिर्फ आज")


def test_chandrabindu_folds_to_anusvara():
    assert normalise_text("हँ") == normalise_text("हं")


def test_fold_pattern_matches_both_spellings():
    pattern = re.compile(fold_pattern("मुनाफ़ा"))
    assert pattern.search(normalise_text("मुनाफ़ा"))
    assert pattern.search(normalise_text("मुनाफा"))


def test_fold_pattern_optional_nukta_syntax_drops_as_a_unit():
    """A pattern may spell an optional nukta as "़?" (nukta + a literal "?"), e.g. 'मुनाफ़?ा'.
    Stripping just the nukta character would leave a bare "?" that makes the *consonant*
    optional instead ('फ़?' -> 'फ?'), which is a silent, wrong change to the pattern."""
    folded = fold_pattern("मुनाफ़?ा")
    assert "?" not in folded  # not "मुनाफ?ा" (फ now optional) - the marker is gone entirely
    pattern = re.compile(folded)
    assert pattern.search(normalise_text("मुनाफ़ा"))
    assert pattern.search(normalise_text("मुनाफा"))

    folded2 = fold_pattern(r"सिर्फ़?\s*आज")
    assert re.search(folded2, normalise_text("सिर्फ़ आज"))
    assert re.search(folded2, normalise_text("सिर्फ आज"))


def test_fold_pattern_maps_chandrabindu_to_anusvara_too():
    assert fold_pattern("हँ") == fold_pattern("हं") == "हं"
