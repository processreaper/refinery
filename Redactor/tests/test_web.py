"""API tests for the FastAPI server, using a stubbed Redactor."""

from __future__ import annotations

import base64
import io
import json
from dataclasses import dataclass

import pytest
from fastapi.testclient import TestClient

from redactor import web


@dataclass
class _FakeMatch:
    start: int
    end: int
    entity_type: str
    score: float = 0.9


class _FakeAnalyzer:
    """Minimal analyzer stub: redacts the literal string 'Alice' as PERSON
    and 'alice@example.com' as EMAIL_ADDRESS, anywhere they appear."""

    needles = [("Alice", "PERSON"), ("alice@example.com", "EMAIL_ADDRESS")]

    def analyze(self, text, language, entities, score_threshold):
        results = []
        for needle, etype in self.needles:
            start = 0
            while True:
                idx = text.find(needle, start)
                if idx < 0:
                    break
                results.append(_FakeMatch(idx, idx + len(needle), etype))
                start = idx + len(needle)
        return sorted(results, key=lambda r: r.start)


@pytest.fixture
def client(monkeypatch):
    from redactor.engine import Redactor

    base = Redactor.__new__(Redactor)
    base.entities = ["PERSON", "EMAIL_ADDRESS"]
    base.score_threshold = 0.4
    base.mapping = {}
    base._faker_locale = "en_US"
    base._analyzer = _FakeAnalyzer()

    monkeypatch.setattr(web, "_redactor_singleton", None)
    monkeypatch.setattr(web, "get_redactor", lambda: base)

    app = web.create_app()
    return TestClient(app)


def test_index_serves_html(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "<title>" in resp.text
    assert "redactor" in resp.text.lower()


def test_entities_endpoint_lists_supported(client):
    resp = client.get("/api/entities")
    assert resp.status_code == 200
    data = resp.json()
    assert "PERSON" in data["entities"]
    assert "EMAIL_ADDRESS" in data["entities"]


def test_redact_text_form(client):
    resp = client.post("/api/redact", data={"text": "Hi Alice, email alice@example.com."})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "text"
    assert "Alice" not in body["text"]
    assert "alice@example.com" not in body["text"]
    assert "Alice" in body["mapping"]["PERSON"]
    assert "alice@example.com" in body["mapping"]["EMAIL_ADDRESS"]


def test_redact_text_file_upload(client):
    files = {"file": ("note.txt", b"contact Alice today", "text/plain")}
    resp = client.post("/api/redact", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "text"
    assert body["filename"] == "note.redacted.txt"
    assert "Alice" not in body["text"]


def test_redact_requires_input(client):
    resp = client.post("/api/redact")
    assert resp.status_code == 400


def test_redact_load_mapping_is_reused(client):
    preset = {"PERSON": {"Alice": "PRESET_NAME"}}
    resp = client.post(
        "/api/redact",
        data={"text": "Hi Alice", "load_mapping": json.dumps(preset)},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "PRESET_NAME" in body["text"]
    assert body["mapping"]["PERSON"]["Alice"] == "PRESET_NAME"


def test_redact_rejects_oversize(client, monkeypatch):
    monkeypatch.setattr(web, "MAX_BYTES", 8)
    files = {"file": ("big.txt", b"this is more than eight bytes", "text/plain")}
    resp = client.post("/api/redact", files=files)
    assert resp.status_code == 413


def test_redact_invalid_load_mapping_returns_400(client):
    resp = client.post(
        "/api/redact",
        data={"text": "hi", "load_mapping": "{not json"},
    )
    assert resp.status_code == 400


def test_redact_docx_returns_binary(client):
    docx = pytest.importorskip("docx")
    doc = docx.Document()
    doc.add_paragraph("Patient Alice was seen.")
    buf = io.BytesIO()
    doc.save(buf)

    files = {"file": (
        "letter.docx",
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )}
    resp = client.post("/api/redact", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "binary"
    assert body["filename"] == "letter.redacted.docx"

    # Decode the returned docx and confirm Alice is gone.
    decoded = base64.b64decode(body["content_b64"])
    out = docx.Document(io.BytesIO(decoded))
    full = "\n".join(p.text for p in out.paragraphs)
    assert "Alice" not in full


def test_output_format_md_flattens_docx_upload(client):
    docx = pytest.importorskip("docx")
    import io as _io
    doc = docx.Document()
    doc.add_heading("Visit", level=1)
    doc.add_paragraph("Patient Alice was seen.")
    buf = _io.BytesIO()
    doc.save(buf)

    files = {"file": (
        "letter.docx",
        buf.getvalue(),
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )}
    resp = client.post("/api/redact", files=files, data={"output_format": "md"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "text"
    assert body["filename"] == "letter.redacted.md"
    assert body["text"].startswith("# Visit")
    assert "Alice" not in body["text"]


def test_output_format_pdf_returns_pdf_bytes(client):
    resp = client.post("/api/redact", data={
        "text": "Hi Alice, email alice@example.com",
        "output_format": "pdf",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "binary"
    assert body["filename"] == "redacted.pdf"
    assert body["content_type"] == "application/pdf"

    raw = base64.b64decode(body["content_b64"])
    assert raw.startswith(b"%PDF-")


def test_output_format_docx_returns_docx_bytes(client):
    docx = pytest.importorskip("docx")
    resp = client.post("/api/redact", data={
        "text": "Hi Alice, email alice@example.com",
        "output_format": "docx",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "binary"
    assert body["filename"] == "redacted.docx"
    assert body["content_type"].endswith("wordprocessingml.document")

    raw = base64.b64decode(body["content_b64"])
    out = docx.Document(io.BytesIO(raw))
    full = "\n".join(p.text for p in out.paragraphs)
    assert "Alice" not in full


def test_output_format_rejects_unknown(client):
    resp = client.post("/api/redact", data={"text": "hi", "output_format": "tarball"})
    assert resp.status_code == 400


def test_pdf_upload_with_original_returns_pdf(client):
    """PDF upload with 'Same as input' must come back as a PDF, not text."""
    from reportlab.lib.pagesizes import LETTER
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate

    src_buf = io.BytesIO()
    SimpleDocTemplate(src_buf, pagesize=LETTER).build([
        Paragraph("Hi Alice.", getSampleStyleSheet()["BodyText"]),
    ])

    files = {"file": ("note.pdf", src_buf.getvalue(), "application/pdf")}
    resp = client.post("/api/redact", files=files, data={"output_format": "original"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "binary"
    assert body["filename"] == "note.redacted.pdf"
    assert body["content_type"] == "application/pdf"

    raw = base64.b64decode(body["content_b64"])
    assert raw.startswith(b"%PDF-")


def test_redact_eml_returns_parseable_eml(client):
    from email import message_from_bytes
    from email.message import EmailMessage
    from email.policy import default as default_policy

    msg = EmailMessage()
    msg["From"] = "Alice <alice@example.com>"
    msg["To"] = "team@example.com"
    msg["Subject"] = "Hi from Alice"
    msg.set_content("Note: alice@example.com is the right email for Alice.")

    files = {"file": ("note.eml", bytes(msg), "message/rfc822")}
    resp = client.post("/api/redact", files=files)
    assert resp.status_code == 200
    body = resp.json()
    assert body["kind"] == "binary"
    assert body["filename"] == "note.redacted.eml"
    assert body["content_type"] == "message/rfc822"

    import base64
    raw = base64.b64decode(body["content_b64"])
    out = message_from_bytes(raw, policy=default_policy)
    assert "Alice" not in str(out["From"])
    assert "alice@example.com" not in str(out["From"])
    assert "Alice" not in out.get_content()


def test_unhandled_exceptions_return_json(monkeypatch):
    """Server-side crashes must return JSON so the SPA can show the message."""
    from redactor import web
    from redactor.engine import Redactor

    base = Redactor.__new__(Redactor)
    base.entities = ["PERSON"]
    base.score_threshold = 0.4
    base.mapping = {}
    base._faker_locale = "en_US"
    base._analyzer = _FakeAnalyzer()

    monkeypatch.setattr(web, "_redactor_singleton", None)
    monkeypatch.setattr(web, "get_redactor", lambda: base)

    def boom(*args, **kwargs):
        raise RuntimeError("simulated failure for test")

    monkeypatch.setattr(web, "_redact_text", boom)

    app = web.create_app()
    crash_client = TestClient(app, raise_server_exceptions=False)
    resp = crash_client.post("/api/redact", data={"text": "anything"})
    assert resp.status_code == 500
    body = resp.json()
    assert "simulated failure for test" in body["detail"]


def test_reverse_swaps_fakes_back(client):
    payload = {
        "text": "Followup with Bob Smith",
        "mapping": {"PERSON": {"Alice": "Bob Smith"}},
    }
    resp = client.post("/api/reverse", json=payload)
    assert resp.status_code == 200
    assert resp.json()["text"] == "Followup with Alice"
