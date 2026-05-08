"""Adapters for email formats: .eml (RFC 822) and Outlook .msg."""

from __future__ import annotations

from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as default_policy
from pathlib import Path
from typing import Callable

Redact = Callable[[str], str]

REDACTABLE_HEADERS = {
    "from",
    "to",
    "cc",
    "bcc",
    "reply-to",
    "sender",
    "subject",
    "delivered-to",
    "x-original-to",
    "return-path",
    "x-sender",
    "x-recipient",
}


def _redact_headers(msg: EmailMessage, redact: Redact) -> None:
    for name in list(msg.keys()):
        if name.lower() not in REDACTABLE_HEADERS:
            continue
        values = msg.get_all(name) or []
        if not values:
            continue
        if len(values) == 1:
            new = redact(str(values[0]))
            if new != str(values[0]):
                msg.replace_header(name, new)
        else:
            new_values = [redact(str(v)) for v in values]
            del msg[name]
            for v in new_values:
                msg[name] = v


def _redact_text_parts(msg: EmailMessage, redact: Redact) -> None:
    for part in msg.walk() if msg.is_multipart() else [msg]:
        if part.is_multipart():
            continue
        ctype = part.get_content_type()
        if not ctype.startswith("text/"):
            continue
        try:
            payload = part.get_content()
        except (LookupError, KeyError, ValueError):
            continue
        if not isinstance(payload, str):
            continue
        new_payload = redact(payload)
        if new_payload != payload:
            subtype = part.get_content_subtype()
            part.set_content(new_payload, subtype=subtype)


def redact_email_message(msg: EmailMessage, redact: Redact) -> None:
    _redact_headers(msg, redact)
    _redact_text_parts(msg, redact)


def redact_eml_file(src: Path, dest: Path, redact: Redact) -> None:
    raw = src.read_bytes()
    msg = message_from_bytes(raw, policy=default_policy)
    redact_email_message(msg, redact)
    dest.write_bytes(bytes(msg))


def _msg_to_email_message(path: Path) -> EmailMessage:
    """Convert a .msg via extract-msg into a Python EmailMessage."""
    import extract_msg

    src = extract_msg.openMsg(str(path))
    em = EmailMessage()
    if src.subject:
        em["Subject"] = src.subject
    if src.sender:
        em["From"] = src.sender
    if src.to:
        em["To"] = src.to
    if src.cc:
        em["Cc"] = src.cc
    if getattr(src, "bcc", None):
        em["Bcc"] = src.bcc
    if src.date:
        em["Date"] = str(src.date)

    body = src.body or ""
    em.set_content(body)

    html = getattr(src, "htmlBody", None)
    if html:
        if isinstance(html, bytes):
            try:
                html = html.decode("utf-8")
            except UnicodeDecodeError:
                html = html.decode("latin-1", errors="replace")
        em.add_alternative(html, subtype="html")
    return em


def redact_msg_file(src: Path, dest: Path, redact: Redact) -> None:
    em = _msg_to_email_message(src)
    redact_email_message(em, redact)
    dest.write_bytes(bytes(em))
