"""Tests for the optional pandoc renderer.

Most of these tests are skipped when pandoc isn't installed on PATH —
the same code path users without pandoc hit.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from redactor import pandoc_render


pandoc_missing = not pandoc_render.is_pandoc_available()
needs_pandoc = pytest.mark.skipif(pandoc_missing, reason="pandoc not installed")


def test_can_render_returns_false_for_unknown_format():
    assert pandoc_render.can_render("definitely-not-a-format") is False


def test_can_render_returns_false_when_pandoc_missing(monkeypatch):
    monkeypatch.setattr(pandoc_render, "is_pandoc_available", lambda: False)
    pandoc_render.can_render.cache_clear() if hasattr(pandoc_render.can_render, "cache_clear") else None
    assert pandoc_render.can_render("docx") is False
    assert pandoc_render.can_render("pdf") is False


@needs_pandoc
def test_render_docx_via_pandoc(tmp_path: Path):
    docx = pytest.importorskip("docx")
    dest = tmp_path / "out.docx"
    pandoc_render.render("# Hello\n\nThis is **bold**.\n", dest, "docx")
    out = docx.Document(str(dest))
    paragraphs = [(p.style.name, p.text) for p in out.paragraphs]
    assert any(style.startswith("Heading") and "Hello" in text
               for style, text in paragraphs)


@needs_pandoc
def test_render_html_via_pandoc(tmp_path: Path):
    dest = tmp_path / "out.html"
    pandoc_render.render("# Hi\n\nA paragraph.\n", dest, "html")
    html = dest.read_text(encoding="utf-8")
    assert "<h1" in html and "Hi" in html
    assert "<p>" in html and "A paragraph" in html


@needs_pandoc
def test_render_rtf_via_pandoc(tmp_path: Path):
    dest = tmp_path / "out.rtf"
    pandoc_render.render("# Hi\n\nBody.\n", dest, "rtf")
    raw = dest.read_text(encoding="utf-8", errors="replace")
    assert raw.startswith("{\\rtf")


@needs_pandoc
def test_dispatch_uses_pandoc_when_available(tmp_path: Path):
    """formats._render_output should prefer pandoc for docx when available."""
    docx = pytest.importorskip("docx")
    from redactor.formats import _render_output

    dest = tmp_path / "out.docx"
    _render_output("# Top\n\nBody.", dest, "docx")
    out = docx.Document(str(dest))
    # If pandoc was used, it preserves heading style names with "Heading" or
    # similar. Either way, the file should contain "Top" and "Body".
    assert any("Top" in p.text for p in out.paragraphs)
    assert any("Body" in p.text for p in out.paragraphs)


def test_pandoc_only_format_raises_when_pandoc_missing(monkeypatch, tmp_path: Path):
    """html/rtf/odt/epub should raise a helpful error when pandoc isn't there."""
    from redactor.formats import _render_output

    monkeypatch.setattr(pandoc_render, "is_pandoc_available", lambda: False)
    pandoc_render.can_render.cache_clear() if hasattr(pandoc_render.can_render, "cache_clear") else None

    with pytest.raises(RuntimeError, match="requires pandoc"):
        _render_output("# Hi\n", tmp_path / "out.html", "html")
