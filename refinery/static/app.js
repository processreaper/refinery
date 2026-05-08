(() => {
  const $ = (sel) => document.querySelector(sel);

  const dropZone = $("#drop-zone");
  const fileInput = $("#file-input");
  const pasteText = $("#paste-text");
  const runBtn = $("#run-btn");
  const status = $("#status");
  const result = $("#result");
  const resultText = $("#result-text");
  const resultNote = $("#result-note");
  const downloadResult = $("#download-result");
  const downloadMapping = $("#download-mapping");
  const copyBtn = $("#copy-btn");
  const mappingBlock = $("#mapping-block");
  const mappingPreview = $("#mapping-preview");
  const redactToggle = $("#redact-toggle");
  const advanced = $("#advanced");
  const toast = $("#toast");

  let chosenFile = null;
  let lastTextResult = "";

  // ---- enable/disable Refine button ----
  const updateRunEnabled = () => {
    runBtn.disabled = !chosenFile && !pasteText.value.trim();
  };

  // ---- file selection (drop + click) ----
  const setFile = (file) => {
    chosenFile = file;
    if (file) {
      $(".dz-primary").textContent = file.name;
      $(".dz-secondary").textContent =
        `${(file.size / 1024).toFixed(1)} KB · ready to refine`;
    } else {
      $(".dz-primary").textContent = "Drop your file here";
      $(".dz-secondary").textContent =
        "PDF · DOCX · PPTX · EML · MSG · TXT · MD  (up to 50 MB)";
    }
    updateRunEnabled();
  };

  ["dragenter", "dragover"].forEach((ev) =>
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropZone.classList.add("drag-over");
    })
  );
  ["dragleave", "dragend", "drop"].forEach((ev) =>
    dropZone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropZone.classList.remove("drag-over");
    })
  );
  dropZone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });
  dropZone.addEventListener("click", (e) => {
    // Don't double-trigger when the user clicks the inner "Choose file" label.
    if (e.target.tagName === "LABEL" || e.target.tagName === "INPUT") return;
    fileInput.click();
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) setFile(e.target.files[0]);
  });
  pasteText.addEventListener("input", updateRunEnabled);

  // ---- redaction toggle: gate the advanced panel ----
  const updateRedactState = () => {
    const on = redactToggle.checked;
    advanced.classList.toggle("hidden", !on);
    if (!on) advanced.open = false;
  };
  redactToggle.addEventListener("change", updateRedactState);
  updateRedactState();

  // ---- entity list ----
  fetch("/api/entities")
    .then((r) => r.json())
    .then(({ entities }) => {
      const sel = $("#entities");
      entities.forEach((e) => {
        const opt = document.createElement("option");
        opt.value = e;
        opt.textContent = e;
        sel.appendChild(opt);
      });
    })
    .catch(() => {});

  // ---- pandoc capability check ----
  fetch("/api/capabilities")
    .then((r) => r.json())
    .then(({ pandoc, pdf_engine }) => {
      const hint = $("#format-hint");
      if (!pandoc) {
        document
          .querySelectorAll("#output-format option[data-needs-pandoc]")
          .forEach((o) => {
            o.disabled = true;
            o.textContent = `${o.textContent} — needs pandoc`;
          });
        hint.textContent =
          'Install pandoc on the server to unlock HTML / RTF / ODT / EPUB.';
      } else {
        const extra = pdf_engine ? `pandoc + ${pdf_engine}` : "pandoc";
        hint.textContent = `Use "Same as input" to keep the original. Renderer: ${extra}.`;
      }
    })
    .catch(() => {});

  // ---- helpers ----
  const setStatus = (msg, kind = "") => {
    status.className = `status ${kind}`;
    if (kind === "loading") {
      status.innerHTML = `<span class="spinner"></span><span>${msg}</span>`;
    } else {
      status.textContent = msg;
    }
  };

  const readJsonFile = (file) =>
    new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        try { resolve(JSON.parse(r.result)); }
        catch (err) { reject(err); }
      };
      r.onerror = () => reject(r.error);
      r.readAsText(file);
    });

  const parseResponse = async (resp) => {
    const text = await resp.text();
    let body;
    try {
      body = text ? JSON.parse(text) : {};
    } catch (_) {
      body = { detail: text || `HTTP ${resp.status} ${resp.statusText}` };
    }
    if (!resp.ok) {
      throw new Error(body.detail || `HTTP ${resp.status} ${resp.statusText}`);
    }
    return body;
  };

  const objectUrl = (data, mime) => URL.createObjectURL(new Blob([data], { type: mime }));

  const showResult = (json) => {
    result.classList.remove("hidden");
    if (json.note) {
      resultNote.textContent = json.note;
      resultNote.classList.remove("hidden");
    } else {
      resultNote.classList.add("hidden");
    }

    if (json.kind === "binary") {
      const bytes = Uint8Array.from(atob(json.content_b64), (c) => c.charCodeAt(0));
      resultText.textContent =
        "[Binary file ready — use Download.]";
      downloadResult.href = objectUrl(bytes, json.content_type || "application/octet-stream");
      lastTextResult = "";
      copyBtn.disabled = true;
      copyBtn.classList.add("disabled");
    } else {
      resultText.textContent = json.text;
      const mime = json.filename && json.filename.endsWith(".html")
        ? "text/html;charset=utf-8"
        : "text/plain;charset=utf-8";
      downloadResult.href = objectUrl(json.text, mime);
      lastTextResult = json.text;
      copyBtn.disabled = false;
      copyBtn.classList.remove("disabled");
    }
    downloadResult.download = json.filename;

    const mapping = json.mapping || {};
    const hasMapping = Object.keys(mapping).length > 0;
    if (hasMapping) {
      const mappingJson = JSON.stringify(mapping, null, 2);
      mappingPreview.textContent = mappingJson;
      downloadMapping.href = objectUrl(mappingJson, "application/json");
      const baseName = (json.filename || "refined").replace(/\.[^.]+$/, "");
      downloadMapping.download = `${baseName}.mapping.json`;
      downloadMapping.classList.remove("hidden");
      mappingBlock.classList.remove("hidden");
    } else {
      downloadMapping.classList.add("hidden");
      mappingBlock.classList.add("hidden");
    }
  };

  // ---- submit ----
  runBtn.addEventListener("click", async () => {
    setStatus("Refining…", "loading");
    runBtn.disabled = true;
    result.classList.add("hidden");

    try {
      const fd = new FormData();
      if (chosenFile) {
        fd.append("file", chosenFile);
      } else {
        fd.append("text", pasteText.value);
      }

      fd.append("redact", redactToggle.checked ? "true" : "false");
      fd.append("output_format", $("#output-format").value);

      if (redactToggle.checked) {
        const selected = Array.from($("#entities").selectedOptions).map((o) => o.value);
        if (selected.length) fd.append("entities", JSON.stringify(selected));

        const t = parseFloat($("#threshold").value);
        if (!Number.isNaN(t)) fd.append("threshold", String(t));

        const mappingFile = $("#load-mapping").files[0];
        if (mappingFile) {
          const obj = await readJsonFile(mappingFile);
          fd.append("load_mapping", JSON.stringify(obj));
        }
      }

      const resp = await fetch("/api/process", { method: "POST", body: fd });
      const json = await parseResponse(resp);
      showResult(json);
      setStatus("Done.", "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      runBtn.disabled = false;
      updateRunEnabled();
    }
  });

  // ---- copy ----
  copyBtn.addEventListener("click", () => {
    if (!lastTextResult) return;
    navigator.clipboard.writeText(lastTextResult).then(() => {
      toast.classList.add("show");
      setTimeout(() => toast.classList.remove("show"), 1800);
    });
  });
})();
