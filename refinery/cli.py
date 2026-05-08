"""Command-line entry point for Refinery — launches the web UI."""

from __future__ import annotations

import argparse
import sys


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="refinery",
        description="Distill documents into a chosen format, optionally redacted.",
    )
    sub = p.add_subparsers(dest="command", required=False)

    s = sub.add_parser("serve", help="Serve the web UI and JSON API.")
    s.add_argument("--host", default="127.0.0.1",
                   help="Bind address. Default 127.0.0.1 (loopback only).")
    s.add_argument("--port", type=int, default=8000, help="Port. Default 8000.")
    s.add_argument("--reload", action="store_true",
                   help="Auto-reload on code changes (development).")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command in (None, "serve"):
        from refinery.web import run

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        reload = getattr(args, "reload", False)
        print(f"refinery: serving on http://{host}:{port}", file=sys.stderr)
        run(host=host, port=port, reload=reload)
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
