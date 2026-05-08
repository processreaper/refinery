"""Engine tests using a stubbed analyzer so they don't need spaCy models."""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from redactor.engine import Redactor


@dataclass
class _FakeMatch:
    start: int
    end: int
    entity_type: str
    score: float = 0.9


class _FakeAnalyzer:
    def __init__(self, matches_per_text):
        self._matches = matches_per_text

    def analyze(self, text, language, entities, score_threshold):
        return list(self._matches.get(text, []))


def _redactor_with(matches_per_text):
    r = Redactor.__new__(Redactor)
    r.entities = ["PERSON", "EMAIL_ADDRESS"]
    r.score_threshold = 0.4
    r.mapping = {}
    r._faker_locale = "en_US"
    r._analyzer = _FakeAnalyzer(matches_per_text)
    return r


def test_redact_replaces_detected_entities():
    text = "Hello Alice Smith, email alice@example.com please."
    matches = [
        _FakeMatch(6, 17, "PERSON"),
        _FakeMatch(25, 42, "EMAIL_ADDRESS"),
    ]
    r = _redactor_with({text: matches})
    result = r.redact(text)

    assert "Alice Smith" not in result.text
    assert "alice@example.com" not in result.text
    assert "Hello " in result.text
    assert " please." in result.text
    assert "Alice Smith" in result.mapping["PERSON"]
    assert "alice@example.com" in result.mapping["EMAIL_ADDRESS"]


def test_same_original_yields_same_fake_within_run():
    text = "Alice met Alice."
    matches = [_FakeMatch(0, 5, "PERSON"), _FakeMatch(10, 15, "PERSON")]
    r = _redactor_with({text: matches})
    result = r.redact(text)

    fake = result.mapping["PERSON"]["Alice"]
    assert result.text == f"{fake} met {fake}."


def test_fake_is_deterministic_across_runs():
    text = "Bob"
    matches = [_FakeMatch(0, 3, "PERSON")]
    r1 = _redactor_with({text: matches})
    r2 = _redactor_with({text: matches})
    assert r1.redact(text).text == r2.redact(text).text


def test_loaded_mapping_is_reused():
    text = "Carol"
    matches = [_FakeMatch(0, 5, "PERSON")]
    r = _redactor_with({text: matches})
    r.mapping = {"PERSON": {"Carol": "PRESET_NAME"}}
    assert r.redact(text).text == "PRESET_NAME"


def test_consistency_pass_replaces_originals_ner_missed():
    """If a name is already mapped, later text containing it gets replaced
    even when NER misses it (e.g., the name is wrapped in HTML markup)."""
    text1 = "Alice met Bob."
    text2 = "<b>Alice</b> says hi to <b>Bob</b>."
    matches1 = [_FakeMatch(0, 5, "PERSON"), _FakeMatch(10, 13, "PERSON")]
    # No NER hits on the HTML text — only the consistency pass should fire.
    r = _redactor_with({text1: matches1, text2: []})

    r.redact(text1)
    out = r.redact(text2)

    assert "Alice" not in out.text
    assert "Bob" not in out.text
    # Same fakes as in the first call (same mapping).
    assert r.mapping["PERSON"]["Alice"] in out.text
    assert r.mapping["PERSON"]["Bob"] in out.text


def test_consistency_pass_skips_self_referential_pairs():
    """Don't replace if the original is a substring of its fake (would loop)."""
    r = _redactor_with({})
    r.mapping = {"PERSON": {"Bob": "Bobby Smith"}}
    out = r.redact("Hello Bob")
    # No NER hit and original ⊂ fake, so no replacement.
    assert out.text == "Hello Bob"


def test_overlapping_matches_first_wins():
    text = "Dr. Carol Smith"
    matches = [
        _FakeMatch(4, 15, "PERSON"),     # "Carol Smith"
        _FakeMatch(4, 9, "PERSON"),      # "Carol" (overlaps, should be skipped)
    ]
    r = _redactor_with({text: matches})
    result = r.redact(text)
    assert "Carol Smith" in result.mapping["PERSON"]
    assert "Carol" not in result.mapping["PERSON"]


def test_empty_text_short_circuits():
    r = _redactor_with({})
    result = r.redact("")
    assert result.text == ""
    assert result.mapping == {}


@pytest.mark.parametrize(
    "entity_type,sample",
    [
        ("PERSON", "Someone Important"),
        ("EMAIL_ADDRESS", "x@y.com"),
        ("PHONE_NUMBER", "555-555-5555"),
        ("US_SSN", "123-45-6789"),
        ("MEDICAL_RECORD_NUMBER", "MRN-1234567"),
        ("CREDIT_CARD", "4111111111111111"),
        ("LOCATION", "Springfield"),
    ],
)
def test_fake_for_returns_nonempty_string(entity_type, sample):
    r = _redactor_with({})
    fake = r._fake_for(entity_type, sample)
    assert isinstance(fake, str) and fake
    assert fake != sample
