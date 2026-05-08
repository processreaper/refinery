import json
from pathlib import Path

from redactor.mapping import load_mapping, reverse_text, save_mapping


def test_save_and_load_roundtrip(tmp_path: Path):
    mapping = {
        "PERSON": {"Alice Smith": "Jane Doe"},
        "EMAIL_ADDRESS": {"alice@example.com": "jane@fake.test"},
    }
    p = tmp_path / "mapping.json"
    save_mapping(p, mapping)
    assert json.loads(p.read_text()) == mapping
    assert load_mapping(p) == mapping


def test_load_missing_returns_empty(tmp_path: Path):
    assert load_mapping(tmp_path / "nope.json") == {}


def test_reverse_text_replaces_fakes_with_originals():
    mapping = {
        "PERSON": {"Alice": "Jane"},
        "EMAIL_ADDRESS": {"alice@example.com": "jane@fake.test"},
    }
    redacted = "Hi Jane, please email jane@fake.test"
    assert reverse_text(redacted, mapping) == "Hi Alice, please email alice@example.com"


def test_reverse_prefers_longest_fake_to_avoid_partial_overlap():
    mapping = {
        "PERSON": {
            "Alice": "Jane",
            "Alice Smith": "Jane Doe",
        },
    }
    # If "Jane" were applied first, "Jane Doe" would become "Alice Doe".
    assert reverse_text("Jane Doe and Jane", mapping) == "Alice Smith and Alice"
