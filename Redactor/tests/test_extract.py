"""Tests for the per-format extractors used when --output-format is txt/md."""

from __future__ import annotations

from email.message import EmailMessage
from pathlib import Path

import pytest

from redactor.extract import (
    _strip_html,
    extract_docx_markdown,
    extract_docx_text,
    extract_eml,
    extract_for_output,
    extract_text_passthrough,
)


def test_strip_html_handles_breaks_paragraphs_and_entities():
    html = "<p>Hello <b>Alice</b>.</p><p>Email&nbsp;<a href='x'>here</a>.</p>"
    out = _strip_html(html)
    assert "Hello Alice." in out
    assert "<" not in out and ">" not in out
    assert "&nbsp;" not in out


def test_extract_docx_text_joins_paragraphs(tmp_path: Path):
    docx = pytest.importorskip("docx")
    p = tmp_path / "in.docx"
    doc = docx.Document()
    doc.add_paragraph("First.")
    doc.add_paragraph("")
    doc.add_paragraph("Second.")
    doc.save(str(p))

    out = extract_docx_text(p)
    assert out.split("\n\n") == ["First.", "Second."]


def test_extract_docx_markdown_uses_heading_styles(tmp_path: Path):
    docx = pytest.importorskip("docx")
    p = tmp_path / "in.docx"
    doc = docx.Document()
    doc.add_heading("Top", level=1)
    doc.add_heading("Sub", level=2)
    doc.add_paragraph("Body.")
    doc.save(str(p))

    out = extract_docx_markdown(p)
    assert "# Top" in out
    assert "## Sub" in out
    assert "Body." in out


def test_extract_eml_renders_headers_then_body(tmp_path: Path):
    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "team@example.com"
    msg["Subject"] = "Hello"
    msg.set_content("Body line.")
    p = tmp_path / "in.eml"
    p.write_bytes(bytes(msg))

    plain = extract_eml(p, markdown=False)
    md = extract_eml(p, markdown=True)

    assert "From: Alice <alice@example.com>" in plain
    assert "Body line." in plain

    assert "**From:** Alice <alice@example.com>" in md
    assert "---" in md
    assert "Body line." in md


def test_extract_for_output_dispatches(tmp_path: Path):
    txt = tmp_path / "x.txt"
    txt.write_text("hello", encoding="utf-8")
    assert extract_for_output(txt, "text", markdown=False) == "hello"
    assert extract_text_passthrough(txt) == "hello"


def test_extract_eml_falls_back_to_html_when_no_plain_text(tmp_path: Path):
    msg = EmailMessage()
    msg["Subject"] = "HTML only"
    msg.set_content("<p>Hi <b>Alice</b>.</p>", subtype="html")
    p = tmp_path / "in.eml"
    p.write_bytes(bytes(msg))

    out = extract_eml(p, markdown=False)
    assert "Hi Alice." in out
    assert "<b>" not in out
