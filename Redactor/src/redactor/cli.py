"""Command-line interface for the redactor."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from redactor.engine import DEFAULT_ENTITIES, Redactor
from redactor.formats import detect_format, extract_pdf_text, redact_file
from redactor.mapping import load_mapping, reverse_text, save_mapping


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="redactor",
        description="Redact PII/PHI from documents and replace with consistent fake values.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("redact", help="Redact a file or stdin.")
    r.add_argument(
        "input",
        nargs="?",
        help="Input file path. Omit (or use '-') to read text from stdin.",
    )
    r.add_argument(
        "-o", "--output",
        help="Output file path. Omit (or use '-') to write text to stdout.",
    )
    r.add_argument(
        "--format",
        choices=["text", "pdf", "docx", "eml", "msg", "auto"],
        default="auto",
        help="Input format. 'auto' uses the file extension (default).",
    )
    r.add_argument(
        "--output-format",
        choices=["original", "txt", "md", "pdf", "docx", "html", "rtf", "odt", "epub"],
        default="original",
        help="Output rendering. 'original' keeps the input's format. "
             "txt / md / pdf / docx work without extra deps. "
             "html / rtf / odt / epub require pandoc on PATH.",
    )
    r.add_argument(
        "--save-mapping",
        metavar="PATH",
        help="Write original->fake mapping to PATH (JSON). Enables reversal.",
    )
    r.add_argument(
        "--load-mapping",
        metavar="PATH",
        help="Pre-load an existing mapping so fakes stay consistent across runs.",
    )
    r.add_argument(
        "--entities",
        nargs="+",
        default=None,
        metavar="ENTITY",
        help=f"Restrict detection to these entity types. Default: all supported. "
             f"Available: {', '.join(DEFAULT_ENTITIES)}",
    )
    r.add_argument(
        "--threshold",
        type=float,
        default=0.4,
        help="Minimum detection confidence (0.0-1.0). Default 0.4.",
    )

    rev = sub.add_parser(
        "reverse",
        help="Replace fake values with their originals using a saved mapping.",
    )
    rev.add_argument("mapping", help="Path to a mapping JSON saved by --save-mapping.")
    rev.add_argument(
        "input",
        nargs="?",
        help="Input file. Omit (or use '-') to read from stdin. Text only.",
    )
    rev.add_argument(
        "-o", "--output",
        help="Output file. Omit (or use '-') to write to stdout.",
    )

    s = sub.add_parser("serve", help="Serve the web UI and JSON API.")
    s.add_argument("--host", default="127.0.0.1",
                   help="Bind address. Default 127.0.0.1 (loopback only).")
    s.add_argument("--port", type=int, default=8000, help="Port. Default 8000.")
    s.add_argument("--reload", action="store_true",
                   help="Auto-reload on code changes (development).")

    return p


def _read_stdin_text() -> str:
    return sys.stdin.read()


def _write_stdout_text(text: str) -> None:
    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")


def _cmd_redact(args: argparse.Namespace) -> int:
    initial_mapping = load_mapping(Path(args.load_mapping)) if args.load_mapping else None
    redactor = Redactor(
        entities=args.entities,
        score_threshold=args.threshold,
        mapping=initial_mapping,
    )

    is_stdin = args.input in (None, "-")
    is_stdout = args.output in (None, "-")

    binary_output_formats = {"pdf", "docx", "rtf", "odt", "epub"}
    text_output_formats = {"txt", "md", "html"}

    if is_stdin:
        if args.format not in ("text", "auto"):
            print(f"error: --format {args.format} requires a file path", file=sys.stderr)
            return 2
        if is_stdout and args.output_format in binary_output_formats:
            print(
                f"error: --output-format {args.output_format} requires -o <path>",
                file=sys.stderr,
            )
            return 2
        result = redactor.redact(_read_stdin_text())
        if is_stdout:
            _write_stdout_text(result.text)
        elif args.output_format in binary_output_formats or args.output_format == "html":
            from redactor.formats import _render_output

            _render_output(result.text, Path(args.output), args.output_format)
        else:
            Path(args.output).write_text(result.text, encoding="utf-8")
    else:
        src = Path(args.input)
        fmt = detect_format(src) if args.format == "auto" else args.format
        if is_stdout:
            if args.output_format in binary_output_formats:
                print(
                    f"error: --output-format {args.output_format} requires -o <path>",
                    file=sys.stderr,
                )
                return 2
            if args.output_format in text_output_formats:
                from redactor.extract import extract_for_output

                text = extract_for_output(
                    src, fmt, markdown=(args.output_format != "txt"),
                )
                if args.output_format == "html":
                    from redactor.formats import _render_output
                    import tempfile

                    with tempfile.NamedTemporaryFile(suffix=".html", delete=False) as tf:
                        tmp = Path(tf.name)
                    try:
                        _render_output(redactor.redact(text).text, tmp, "html")
                        sys.stdout.write(tmp.read_text(encoding="utf-8"))
                    finally:
                        tmp.unlink(missing_ok=True)
                else:
                    _write_stdout_text(redactor.redact(text).text)
            elif fmt in ("docx", "msg"):
                print(f"error: {fmt} output requires -o <path>", file=sys.stderr)
                return 2
            elif fmt == "eml":
                from email import message_from_bytes
                from email.policy import default as default_policy
                from redactor.email_format import redact_email_message

                msg = message_from_bytes(src.read_bytes(), policy=default_policy)
                redact_email_message(msg, lambda t: redactor.redact(t).text)
                sys.stdout.buffer.write(bytes(msg))
            else:
                text = extract_pdf_text(src) if fmt == "pdf" else src.read_text(encoding="utf-8")
                _write_stdout_text(redactor.redact(text).text)
        else:
            redact_file(
                src,
                Path(args.output),
                lambda t: redactor.redact(t).text,
                fmt=fmt,
                output_format=args.output_format,
            )

    if args.save_mapping:
        save_mapping(Path(args.save_mapping), redactor.mapping)

    return 0


def _cmd_reverse(args: argparse.Namespace) -> int:
    mapping = load_mapping(Path(args.mapping))
    is_stdin = args.input in (None, "-")
    is_stdout = args.output in (None, "-")
    text = _read_stdin_text() if is_stdin else Path(args.input).read_text(encoding="utf-8")
    out = reverse_text(text, mapping)
    if is_stdout:
        _write_stdout_text(out)
    else:
        Path(args.output).write_text(out, encoding="utf-8")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    from redactor.web import run

    print(f"redactor: serving on http://{args.host}:{args.port}", file=sys.stderr)
    run(host=args.host, port=args.port, reload=args.reload)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "redact":
        return _cmd_redact(args)
    if args.command == "reverse":
        return _cmd_reverse(args)
    if args.command == "serve":
        return _cmd_serve(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
