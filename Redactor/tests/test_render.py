"""Tests for the markdown -> PDF / DOCX renderers."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from redactor.render import (
    _add_emphasis_runs,
    _markdown_to_reportlab_html,
    render_markdown_to_docx,
    render_markdown_to_pdf,
)


def test_markdown_to_reportlab_html_escapes_then_emphasizes():
    out = _markdown_to_reportlab_html("Hi **Alice** & <Bob> *team*")
    assert "&amp;" in out
    assert "&lt;Bob&gt;" in out
    assert "<b>Alice</b>" in out
    assert "<i>team</i>" in out


def test_render_markdown_to_pdf_writes_valid_pdf(tmp_path: Path):
    md = "# Title\n\nHello **bold** and *italic* text.\n\n- one\n- two\n"
    dest = tmp_path / "out.pdf"
    render_markdown_to_pdf(md, dest)

    data = dest.read_bytes()
    assert data.startswith(b"%PDF-")
    assert data.rstrip().endswith(b"%%EOF") or b"%%EOF" in data[-64:]


def test_render_markdown_to_docx_preserves_headings_and_bullets(tmp_path: Path):
    docx = pytest.importorskip("docx")
    md = "# Top\n\n## Sub\n\nA paragraph with **bold** text.\n\n- alpha\n- beta\n"
    dest = tmp_path / "out.docx"
    render_markdown_to_docx(md, dest)

    out = docx.Document(str(dest))
    paragraphs = [(p.style.name, p.text) for p in out.paragraphs]

    styles = [s for s, _ in paragraphs]
    texts = [t for _, t in paragraphs]
    assert "Heading 1" in styles
    assert "Heading 2" in styles
    assert "List Bullet" in styles

    body = next(p for p in out.paragraphs if p.text.startswith("A paragraph"))
    bold_runs = [r for r in body.runs if r.bold]
    assert any(r.text == "bold" for r in bold_runs)

    assert any("Top" in t for t in texts)
    assert any("alpha" in t for t in texts)


def test_add_emphasis_runs_handles_mixed_spans():
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    p = doc.add_paragraph()
    _add_emphasis_runs(p, "plain **bold** mid *italic* end")
    runs = [(r.text, bool(r.bold), bool(r.italic)) for r in p.runs]
    assert ("plain ", False, False) in runs
    assert ("bold", True, False) in runs
    assert ("italic", False, True) in runs
    assert (" end", False, False) in runs
