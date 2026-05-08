"""Optional Pandoc-backed renderer.

Used when the system `pandoc` binary is installed. Produces higher-quality
output for DOCX and unlocks RTF / ODT / HTML / EPUB. Falls back to the
built-in reportlab + python-docx renderers when pandoc isn't available.

PDF via pandoc requires a separate PDF engine (LaTeX, weasyprint, or
wkhtmltopdf). If none is found we let the caller fall back to reportlab.
"""

from __future__ import annotations

import logging
import shutil
from functools import lru_cache
from pathlib import Path

log = logging.getLogger(__name__)

# Output formats pandoc can produce (when available). PDF is conditional —
# only when a PDF engine is also installed.
PANDOC_FORMATS = {"docx", "rtf", "odt", "html", "epub"}

# PDF engines pandoc supports, in our preferred order. weasyprint is pure
# Python (no LaTeX install needed) and ships nicely. Fall through to LaTeX
# engines if the user has them, then wkhtmltopdf as a last resort.
PDF_ENGINES = ("weasyprint", "xelatex", "lualatex", "pdflatex", "wkhtmltopdf", "context")


@lru_cache(maxsize=1)
def is_pandoc_available() -> bool:
    """True if pypandoc imports and a pandoc binary is on PATH."""
    try:
        import pypandoc

        pypandoc.get_pandoc_path()
        return True
    except (ImportError, OSError):
        return False


@lru_cache(maxsize=1)
def find_pdf_engine() -> str | None:
    for engine in PDF_ENGINES:
        if shutil.which(engine):
            return engine
    return None


def can_render(output_format: str) -> bool:
    """True if pandoc can produce `output_format` on this machine."""
    if not is_pandoc_available():
        return False
    if output_format == "pdf":
        return find_pdf_engine() is not None
    return output_format in PANDOC_FORMATS


def render(markdown_text: str, dest: Path, output_format: str) -> None:
    """Render redacted markdown to `dest` using pandoc.

    Caller should call `can_render(output_format)` first; this raises
    RuntimeError if the format isn't supported on this machine.
    """
    if not can_render(output_format):
        raise RuntimeError(f"pandoc cannot render {output_format} on this machine")

    import pypandoc

    extra_args: list[str] = ["--standalone"]
    if output_format == "pdf":
        engine = find_pdf_engine()
        if engine is None:  # defensive — can_render already checked
            raise RuntimeError("no PDF engine available for pandoc")
        extra_args.append(f"--pdf-engine={engine}")

    log.info("Rendering with pandoc -> %s (extra_args=%s)", output_format, extra_args)
    pypandoc.convert_text(
        markdown_text,
        to=output_format,
        format="markdown",
        outputfile=str(dest),
        extra_args=extra_args,
    )
