"""Tests for .eml redaction. Uses a literal-replacement redactor (no spaCy)."""

from __future__ import annotations

from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as default_policy
from pathlib import Path

import pytest

from redactor.email_format import redact_email_message, redact_eml_file


def _redact(text: str) -> str:
    return (
        text.replace("Alice Smith", "Sarah Cook")
        .replace("alice@example.com", "fake@redacted.test")
        .replace("Dr. Bob Jones", "Lisa Anderson")
    )


def _build_simple_eml() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Alice Smith <alice@example.com>"
    msg["To"] = "Dr. Bob Jones <bob@hospital.example>"
    msg["Subject"] = "Hello from Alice Smith"
    msg["Message-ID"] = "<original-id@example.com>"
    msg["Date"] = "Wed, 01 Jan 2025 10:00:00 -0500"
    msg.set_content("Hi Bob, this is Alice Smith. Please reach me at alice@example.com.")
    return bytes(msg)


def _build_multipart_eml() -> bytes:
    msg = EmailMessage()
    msg["From"] = "Alice Smith <alice@example.com>"
    msg["To"] = "team@example.com"
    msg["Subject"] = "Multipart from Alice Smith"
    msg.set_content("Plain: contact Alice Smith at alice@example.com.")
    msg.add_alternative(
        "<p>HTML: contact <b>Alice Smith</b> at "
        "<a href='mailto:alice@example.com'>alice@example.com</a>.</p>",
        subtype="html",
    )
    return bytes(msg)


def test_redact_email_message_rewrites_targeted_headers():
    msg = message_from_bytes(_build_simple_eml(), policy=default_policy)
    redact_email_message(msg, _redact)

    assert "Alice Smith" not in str(msg["From"])
    assert "alice@example.com" not in str(msg["From"])
    assert "Sarah Cook" in str(msg["From"])
    assert "Dr. Bob Jones" not in str(msg["To"])
    assert "Sarah Cook" in str(msg["Subject"])
    # Message-ID must be left structural & untouched.
    assert msg["Message-ID"] == "<original-id@example.com>"


def test_redact_email_message_rewrites_text_body():
    msg = message_from_bytes(_build_simple_eml(), policy=default_policy)
    redact_email_message(msg, _redact)

    body = msg.get_content()
    assert "Alice Smith" not in body
    assert "alice@example.com" not in body
    assert "Sarah Cook" in body
    assert "fake@redacted.test" in body


def test_redact_email_message_rewrites_all_text_parts_in_multipart():
    msg = message_from_bytes(_build_multipart_eml(), policy=default_policy)
    redact_email_message(msg, _redact)

    parts = list(msg.walk())
    text_payloads = [p.get_content() for p in parts if not p.is_multipart()]
    assert text_payloads, "expected at least one text part"
    for payload in text_payloads:
        assert "Alice Smith" not in payload
        assert "alice@example.com" not in payload


def test_redact_eml_file_round_trip(tmp_path: Path):
    src = tmp_path / "in.eml"
    dest = tmp_path / "out.eml"
    src.write_bytes(_build_simple_eml())

    redact_eml_file(src, dest, _redact)

    out = message_from_bytes(dest.read_bytes(), policy=default_policy)
    assert "Sarah Cook" in str(out["From"])
    assert "Alice Smith" not in out.get_content()


def test_returned_eml_is_parseable(tmp_path: Path):
    src = tmp_path / "in.eml"
    dest = tmp_path / "out.eml"
    src.write_bytes(_build_multipart_eml())

    redact_eml_file(src, dest, _redact)

    out = message_from_bytes(dest.read_bytes(), policy=default_policy)
    # multipart/alternative with two text parts should still be intact
    assert out.is_multipart()
    subtypes = sorted(p.get_content_subtype() for p in out.walk() if not p.is_multipart())
    assert subtypes == ["html", "plain"]
