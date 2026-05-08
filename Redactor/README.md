# redactor

Strip personal data out of documents before you send them to an AI.

`redactor` finds names, emails, phone numbers, SSNs, addresses, medical record
numbers and other identifiers in your text — and replaces each one with a
realistic, **consistent** fake. The same `Alice Smith` becomes the same
`Sarah Cook` everywhere in the document (and across documents, if you save
the mapping). The output reads like the original; the AI never sees a real
identifier.

When the AI replies, you can flip the mapping back to recover the originals.

## Why use this

- **Sharing logs / notes / tickets with an LLM** without leaking customer data.
- **Healthcare workflows** where PHI ([HIPAA Safe Harbor identifiers][hipaa])
  shouldn't reach a third-party model.
- **Code reviews / debugging** with snippets that contain real credentials,
  emails, or stack traces.
- **Email triage** — `.eml` and Outlook `.msg` files are first-class inputs.

[hipaa]: https://www.hhs.gov/hipaa/for-professionals/privacy/special-topics/de-identification/index.html

## Install (macOS)

```bash
# 1. Clone (if you haven't already) — see the GitHub auth section below
git clone https://github.com/phant0mbot/redactor.git ~/redactor
cd ~/redactor

# 2. Python 3.9+ in a venv
python3 -m venv .venv
source .venv/bin/activate

# 3. Install the package and its NER model
pip install -e .
python -m spacy download en_core_web_sm

# 4. (Optional, recommended) install pandoc for nicer DOCX/PDF + extra formats
brew install pandoc            # unlocks html / rtf / odt / epub
pip install weasyprint         # lets pandoc render PDFs without LaTeX
```

Every new shell: `cd ~/redactor && source .venv/bin/activate` before running.

If `pip install -e .` fails on macOS, run `xcode-select --install` and retry —
the C build tools are usually missing.

### Cloning a private repo

If you don't already have GitHub set up, the simplest path is GitHub's CLI:

```bash
brew install gh
gh auth login                  # browser flow, choose HTTPS + Git auth
gh repo clone phant0mbot/redactor ~/redactor
```

## Quick start

```bash
echo "Email Alice at alice@example.com" | python -m redactor redact
# Email Sarah Cook at zbean@example.org
```

```bash
python -m redactor serve
# open http://127.0.0.1:8000  ← drag-and-drop UI
```

## Command reference

All commands run as `python -m redactor <subcommand>`.

### `redact` — redact a file or stdin

```bash
python -m redactor redact [INPUT] [-o OUTPUT] [options]
```

| Argument / flag | What it does |
| --- | --- |
| `INPUT` | File path. Omit (or use `-`) to read from stdin (text only). |
| `-o, --output PATH` | Where to write the result. Omit (or `-`) for stdout (text only). |
| `--format {auto,text,pdf,docx,eml,msg}` | Force the input parser. `auto` (default) uses the file extension. |
| `--output-format {original,txt,md,pdf,docx,html,rtf,odt,epub}` | Render the output as. `original` (default) keeps the input's format. `html / rtf / odt / epub` require pandoc. |
| `--entities ENTITY [ENTITY ...]` | Restrict detection. Defaults to all supported types. |
| `--threshold FLOAT` | Detection confidence cutoff (0.0–1.0, default 0.4). Lower = more catches + more false positives. |
| `--save-mapping PATH` | Write the original→fake mapping to a JSON sidecar. Required for un-redacting later. |
| `--load-mapping PATH` | Pre-load a mapping so the same originals get the same fakes (use this to keep multiple documents consistent). |

Examples:

```bash
# stdin → stdout (great for piping)
cat notes.md | python -m redactor redact > notes.redacted.md

# DOCX → DOCX, preserving paragraph structure, with a saved mapping
python -m redactor redact letter.docx -o letter.redacted.docx --save-mapping map.json

# PDF → PDF (re-typeset; original layout isn't preserved)
python -m redactor redact report.pdf -o report.redacted.pdf

# Email → email (.eml in, .eml out; .msg comes out as a redacted .eml)
python -m redactor redact mail.eml   -o mail.redacted.eml
python -m redactor redact mail.msg   -o mail.redacted.eml

# Force a different output format
python -m redactor redact letter.docx -o letter.html --output-format html      # needs pandoc
python -m redactor redact mail.eml    -o mail.epub   --output-format epub      # needs pandoc
python -m redactor redact letter.docx -o letter.md   --output-format md
```

### `reverse` — un-redact text using a saved mapping

```bash
python -m redactor reverse MAPPING [INPUT] [-o OUTPUT]
```

```bash
# Pipe an AI's reply through it
cat ai_reply.txt | python -m redactor reverse map.json
# → original names and emails restored
```

### `serve` — run the web UI + JSON API

```bash
python -m redactor serve [--host 127.0.0.1] [--port 8000] [--reload]
```

| Flag | Default | What it does |
| --- | --- | --- |
| `--host` | `127.0.0.1` | Bind address. **Loopback only by default** because uploads contain real PII. |
| `--port` | `8000` | Port. |
| `--reload` | off | Auto-restart on code changes (development). |

Then open <http://127.0.0.1:8000>. The UI has two tabs: **Redact** (drag-drop
or paste, configure entities/threshold/output format, download the redacted
file plus the mapping) and **Reverse** (upload a mapping JSON + paste text to
get originals back).

## Web UI from the JSON API

```
GET  /api/entities       → list of detectable entity types
GET  /api/capabilities   → { "pandoc": true|false, "pdf_engine": "weasyprint"|... }
POST /api/redact         → multipart: file or text + options
POST /api/reverse        → JSON: { "text", "mapping" }
```

`/api/redact` accepts (as form fields):

- `file` — uploaded document, **or** `text` — string to redact
- `output_format` — same choices as the CLI flag
- `entities` — JSON array of entity types
- `threshold` — float
- `load_mapping` — JSON object to seed cross-run consistency

It returns JSON with either `kind: "text"` (preview-able formats: txt / md /
html) or `kind: "binary"` (PDF / DOCX / RTF / ODT / EPUB), plus the
original→fake mapping. Upload limit: 10 MB.

## Library use

```python
from redactor import Redactor

r = Redactor()
result = r.redact("Hi Alice, your MRN is 1234567.")
print(result.text)     # "Hi Sarah Cook, your MRN-09594459."
print(result.mapping)  # {"PERSON": {"Alice": "Sarah Cook"}, ...}

# Cross-run consistency: pass the previous mapping in
r2 = Redactor(mapping=result.mapping)
```

## What gets detected

Built on [Microsoft Presidio][presidio] (regex + checksums) and spaCy NER
(names, places), with extra recognizers for things Presidio misses out of
the box.

| Category | Entity types |
| --- | --- |
| **PII** | `PERSON`, `EMAIL_ADDRESS`, `PHONE_NUMBER`, `LOCATION`, `DATE_TIME`, `URL`, `IP_ADDRESS`, `CREDIT_CARD`, `IBAN_CODE`, `CRYPTO`, `NRP` (nationality / religion / politics) |
| **US identifiers** | `US_SSN`, `US_ITIN`, `US_DRIVER_LICENSE`, `US_PASSPORT`, `US_BANK_NUMBER` |
| **PHI / health** | `MEDICAL_LICENSE`, `MEDICAL_RECORD_NUMBER`, `HEALTH_PLAN_NUMBER` |

Once a value has been mapped (this run, or a loaded mapping), every later
occurrence is replaced with the same fake — even when NER would have missed
the later occurrence (e.g. a name buried inside HTML markup). New recognizers
can be added in `src/redactor/recognizers.py`.

[presidio]: https://microsoft.github.io/presidio/

## Output format details

`redactor` reads many formats and renders to many. Here's how each
combination behaves:

| Output format | Renderer | Notes |
| --- | --- | --- |
| `original` | Format-specific | DOCX→DOCX preserves paragraph structure; EML→EML preserves MIME structure; PDF→PDF re-typesets via reportlab/pandoc. |
| `txt` | Built-in | Always-on. Plain UTF-8. |
| `md` | Built-in | Always-on. DOCX heading styles → `#`; email headers → `**From:** …` block. |
| `pdf` | pandoc (preferred) → reportlab | Pandoc + weasyprint or LaTeX gives nicer typography; reportlab is the always-on fallback. |
| `docx` | pandoc (preferred) → python-docx | Pandoc preserves heading styles, lists, tables better; python-docx fallback handles the basics. |
| `html` | pandoc only | Standalone HTML with pandoc's stylesheet. |
| `rtf` | pandoc only | |
| `odt` | pandoc only | OpenDocument Text. |
| `epub` | pandoc only | |

`http://127.0.0.1:8000/api/capabilities` reports whether pandoc and a PDF
engine are available on your machine.

## Limitations

- **PDF round-trips don't preserve the original's layout.** We extract text,
  redact it, and re-render. Fonts, images, columns, and tables don't survive.
  Use `--output-format txt|md` if you'd rather have the redacted text directly.
- **DOCX preserves paragraph structure but collapses run-level formatting**
  in `original` mode (bold/italic spans inside a paragraph), because entity
  boundaries don't align with run boundaries.
- **NER is fuzzy.** spaCy's small model occasionally tags ordinary words
  (`Email`, `Patient`) as `PERSON`, and may miss unusual names. Tune with
  `--threshold` or `--entities`.
- **Mapping files are as sensitive as the original document.** Each entry
  pairs a real value with its fake. Don't commit them; store encrypted;
  delete when the conversation ends.

## Reversibility

The mapping is what makes this reversible. By default no mapping is saved —
within a single run the redactions are still consistent (same input value →
same fake), but afterwards there's no way to un-redact.

Pass `--save-mapping path.json` to keep one. Then later you can:

```bash
python -m redactor reverse path.json < ai_reply.txt > ai_reply.real.txt
```

`--load-mapping` plus `--save-mapping` on every run gives you a single
growing mapping that stays consistent across all your documents.

## Tests

```bash
python -m pytest
```

The pandoc-specific tests skip when pandoc isn't on PATH, so the suite
passes whether or not you've installed it.

## Project layout

```
src/redactor/
  engine.py          # Core redactor: Presidio analyzer + Faker-backed fakes
  recognizers.py     # Extra PII/PHI recognizers (MRN, health plan, …)
  formats.py         # Per-format read/write + output-format dispatch
  email_format.py    # .eml / .msg redaction
  extract.py         # Text/markdown extractors per input format
  render.py          # Built-in PDF (reportlab) + DOCX (python-docx) renderers
  pandoc_render.py   # Optional pandoc renderer (used when available)
  mapping.py         # Save/load mapping JSON, reverse helper
  cli.py             # `python -m redactor …` entry points
  web.py             # FastAPI app + drag-drop UI + /api/redact, /api/reverse
  static/            # SPA: HTML / CSS / vanilla JS
tests/               # pytest suite
```
