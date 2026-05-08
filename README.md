```
                ██████╗ ███████╗███████╗██╗███╗   ██╗███████╗██████╗ ██╗   ██╗
                ██╔══██╗██╔════╝██╔════╝██║████╗  ██║██╔════╝██╔══██╗╚██╗ ██╔╝
                ██████╔╝█████╗  █████╗  ██║██╔██╗ ██║█████╗  ██████╔╝ ╚████╔╝
                ██╔══██╗██╔══╝  ██╔══╝  ██║██║╚██╗██║██╔══╝  ██╔══██╗  ╚██╔╝
                ██║  ██║███████╗██║     ██║██║ ╚████║███████╗██║  ██║   ██║
                ╚═╝  ╚═╝╚══════╝╚═╝     ╚═╝╚═╝  ╚═══╝╚══════╝╚═╝  ╚═╝   ╚═╝
                          distill ·  redact ·  convert
                  ┌──────────────────────────────────────────────┐
                  │   in:  pdf · docx · pptx · eml · msg · txt   │
                  │  out:  md  · txt  · pdf  · docx · html · …   │
                  └──────────────────────────────────────────────┘
```

A local web tool that **distills** input documents into a chosen format and
**optionally redacts** PII / PHI on the way through.

Drag-and-drop interface. One toggle for redaction. Output to Markdown, plain
text, PDF, Word, or — when pandoc is installed — HTML, RTF, ODT, EPUB.

## Features

- **Inputs**: `.pdf`, `.docx`, `.pptx`, `.eml`, `.msg`, `.txt`, `.md`, source files
- **Outputs**: Markdown, plain text, PDF, DOCX, HTML, RTF, ODT, EPUB, or "same
  as input" (preserves DOCX / PPTX / EML structure when redacting in place)
- **Redaction toggle**: when on, names, emails, SSNs, MRNs, phone numbers and
  other identifiers are replaced with consistent fakes (`Alice` → `Sarah Cook`
  everywhere). When off, Refinery just extracts and reformats.
- **Advanced options**: confidence threshold, restrict to specific entity
  types, reuse a mapping JSON for cross-document consistency.

---

## Quick start

Refinery needs **Python 3.9+**. The same three-step pattern (venv → install →
serve) works on every platform; only the shell commands differ.

### macOS

```bash
git clone <this-repo> refinery && cd refinery
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m spacy download en_core_web_sm

# Optional — unlocks HTML / RTF / ODT / EPUB and nicer DOCX
brew install pandoc
pip install weasyprint        # lets pandoc render PDFs without LaTeX

refinery serve                # open http://127.0.0.1:8000
```

If `pip install -e .` fails with a build error, run `xcode-select --install`
first — the Apple command-line tools are usually missing.

### Linux

```bash
git clone <this-repo> refinery && cd refinery
python3 -m venv .venv
source .venv/bin/activate
pip install -e .
python -m spacy download en_core_web_sm

# Optional — Debian/Ubuntu
sudo apt-get install -y pandoc
pip install weasyprint

# Optional — Fedora/RHEL
sudo dnf install -y pandoc
pip install weasyprint

# Optional — Arch
sudo pacman -S pandoc
pip install weasyprint

refinery serve                # open http://127.0.0.1:8000
```

If a wheel build fails (lxml, cryptography, reportlab), install the toolchain:

```bash
# Debian/Ubuntu
sudo apt-get install -y build-essential python3-dev libxml2-dev libxslt1-dev

# Fedora/RHEL
sudo dnf install -y gcc gcc-c++ python3-devel libxml2-devel libxslt-devel
```

### Windows

PowerShell (recommended):

```powershell
git clone <this-repo> refinery
cd refinery
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e .
python -m spacy download en_core_web_sm

# Optional — pandoc via winget (or download from https://pandoc.org/installing.html)
winget install --id JohnMacFarlane.Pandoc
pip install weasyprint

refinery serve
# open http://127.0.0.1:8000
```

If PowerShell blocks `Activate.ps1`, allow it for the current user:

```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Command Prompt is the same flow with `.venv\Scripts\activate.bat` instead.

WSL2 users should follow the **Linux** instructions inside the WSL shell — it's
the smoothest path on Windows.

### Verify it's working

Once the server is running, in a second terminal:

```bash
curl -s http://127.0.0.1:8000/api/capabilities
# → {"pandoc": true|false, "pdf_engine": "weasyprint"|null}
```

Or just open the page and drop a file in.

### CLI flags

```
refinery serve [--host HOST] [--port PORT] [--reload]
```

| Flag       | Default       | Notes                                                 |
| ---------- | ------------- | ----------------------------------------------------- |
| `--host`   | `127.0.0.1`   | Loopback only by default. Set `0.0.0.0` to expose it. |
| `--port`   | `8000`        |                                                       |
| `--reload` | off           | Auto-restart on code changes (development only).      |

`python -m refinery serve` works identically if the `refinery` script isn't on
your PATH.

---

## Self-hosting on a server

Refinery is a single FastAPI app. The deployment shape is whatever you'd use
for any small Python web service: a venv, a process supervisor, a reverse
proxy, and TLS. **Refinery has no built-in authentication** — anyone who can
reach the port can upload documents and read results, so put auth in front.

### 1. Install on the server

```bash
sudo adduser --system --group --home /opt/refinery refinery
sudo -u refinery -H bash <<'EOF'
cd /opt/refinery
git clone <this-repo> .
python3 -m venv .venv
.venv/bin/pip install -e .
.venv/bin/python -m spacy download en_core_web_sm
EOF
```

(Optional) install pandoc + a PDF engine system-wide:

```bash
sudo apt-get install -y pandoc
sudo -u refinery /opt/refinery/.venv/bin/pip install weasyprint
```

### 2. Run under systemd

Create `/etc/systemd/system/refinery.service`:

```ini
[Unit]
Description=Refinery document distillation web service
After=network.target

[Service]
Type=simple
User=refinery
Group=refinery
WorkingDirectory=/opt/refinery
ExecStart=/opt/refinery/.venv/bin/refinery serve --host 127.0.0.1 --port 8000
Restart=on-failure
RestartSec=3

# Hardening
NoNewPrivileges=yes
PrivateTmp=yes
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/opt/refinery
ProtectKernelTunables=yes
ProtectKernelModules=yes
ProtectControlGroups=yes
RestrictAddressFamilies=AF_INET AF_INET6
LockPersonality=yes

[Install]
WantedBy=multi-user.target
```

Bring it up:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now refinery
sudo systemctl status refinery
journalctl -u refinery -f
```

Refinery binds to `127.0.0.1`; the proxy below is what makes it reachable.

### 3. Reverse-proxy with TLS

Pick whichever proxy you already use. The shape is the same: terminate TLS,
forward to `127.0.0.1:8000`, and gate access.

**Caddy** (`/etc/caddy/Caddyfile`) — TLS is automatic via Let's Encrypt:

```
refinery.example.com {
    encode gzip
    # Auth — pick one:
    # basic_auth { alice $2a$14$… }   # bcrypt; generate with `caddy hash-password`
    # forward_auth oauth2-proxy:4180 { uri /oauth2/auth }

    # Match Refinery's 50 MB upload limit
    request_body { max_size 50MB }

    reverse_proxy 127.0.0.1:8000
}
```

**nginx** (`/etc/nginx/sites-available/refinery`):

```nginx
server {
    listen 443 ssl http2;
    server_name refinery.example.com;

    ssl_certificate     /etc/letsencrypt/live/refinery.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/refinery.example.com/privkey.pem;

    client_max_body_size 50M;          # match the app's upload cap
    proxy_read_timeout   300s;         # PDF rendering can be slow

    # Auth — pick one:
    # auth_basic           "Refinery";
    # auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}

server {
    listen 80;
    server_name refinery.example.com;
    return 301 https://$host$request_uri;
}
```

Get a cert with `sudo certbot --nginx -d refinery.example.com`, then
`sudo systemctl reload nginx`.

### 4. Operational notes

- **Resource sizing.** spaCy + Presidio load into memory once (~500 MB RSS) and
  stay there. A 1 vCPU / 1 GB box is enough for a small team; bump to 2 GB if
  you expect concurrent large PDFs.
- **First request is slow.** The spaCy model loads lazily on first redact —
  expect a 3-5 s warm-up. Ping `/api/process` once after deploy to pre-warm.
- **Upload cap.** Refinery itself caps uploads at 50 MB (`MAX_BYTES` in
  `refinery/web.py`). Make sure your reverse proxy's body limit matches.
- **Mapping files are sensitive.** They pair real identifiers with their
  fakes — treat them as carefully as the source document. Don't log them, and
  don't persist them on the server unless you have to.
- **Public exposure.** Refinery has no auth, no rate limiting, no audit log.
  Always run it behind a proxy that handles those, or keep it on a private
  network / VPN.
- **Updating.** `cd /opt/refinery && sudo -u refinery git pull && sudo -u refinery .venv/bin/pip install -e . && sudo systemctl restart refinery`.

---

## How it works

1. **Extract** — each input format has a dedicated extractor that produces
   plain text or Markdown (DOCX heading styles → `#`; PPTX slides → `## Slide N`
   with bullet hierarchy; emails → header block + body).
2. **(Optional) redact** — Microsoft Presidio + spaCy NER detect entities;
   `Faker` produces deterministic, consistent fake replacements, seeded by a
   hash of `(entity_type, original)` so the same input always maps to the
   same fake.
3. **Render** — Markdown is written as-is, or rendered through pandoc (when
   available) or built-in fallbacks (`reportlab` for PDF, `python-docx` for
   DOCX).

## API

- `GET  /api/entities`     — list of detectable entity types
- `GET  /api/capabilities` — `{ "pandoc": true|false, "pdf_engine": "..." | null }`
- `POST /api/process`      — multipart form: `file` or `text`, plus
  `redact` (true/false), `output_format`, `entities`, `threshold`, `load_mapping`
- `POST /api/reverse`      — JSON `{ text, mapping }` → `{ text }` with originals restored

## Layout

```
refinery/
  engine.py        Presidio + Faker redaction engine
  recognizers.py   Extra PII/PHI recognizers (MRN, health plan, SSN)
  extract.py       Per-format extractors (PDF, DOCX, PPTX, EML, MSG, text)
  formats.py       Format dispatcher + in-place redactors
  render.py        Built-in PDF / DOCX renderers
  pandoc_render.py Optional pandoc-backed renderer
  email_format.py  .eml / .msg redaction
  mapping.py       Mapping JSON load/save + reverse helper
  cli.py           `refinery serve` entry point
  web.py           FastAPI app
  static/          HTML / CSS / vanilla JS UI
```

## Notes

- PDF round-trips don't preserve the original layout — text is extracted and
  re-rendered.
- Mapping files contain the original→fake pairs and are as sensitive as the
  source document.
- Refinery binds to `127.0.0.1` by default. Don't expose it to the public
  internet without authentication.
