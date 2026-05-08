(() => {
  const $ = (sel) => document.querySelector(sel);

  // ----- tab switching -----
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("active"));
      document.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      tab.classList.add("active");
      document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    });
  });

  // ----- entity list -----
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
    });

  // ----- capabilities (pandoc availability) -----
  fetch("/api/capabilities")
    .then((r) => r.json())
    .then(({ pandoc, pdf_engine }) => {
      const hint = $("#output-format-hint");
      if (!pandoc) {
        document
          .querySelectorAll("#output-format option[data-needs-pandoc]")
          .forEach((o) => {
            o.disabled = true;
            o.textContent = `${o.textContent} — install pandoc to enable`;
          });
        hint.textContent =
          "Install pandoc on the server to unlock HTML / RTF / ODT / EPUB.";
      } else {
        const extra = pdf_engine ? `pandoc + ${pdf_engine} engine` : "pandoc";
        hint.textContent = `Override to render the redacted output. Using ${extra} for richer output where supported.`;
      }
    })
    .catch(() => {});

  // ----- dropzone -----
  const dropzone = $("#dropzone");
  const fileInput = $("#file-input");
  const pasteText = $("#paste-text");
  const redactBtn = $("#redact-btn");
  let chosenFile = null;

  const updateRedactEnabled = () => {
    redactBtn.disabled = !chosenFile && !pasteText.value.trim();
  };

  const setFile = (file) => {
    chosenFile = file;
    if (file) {
      $(".dz-primary").textContent = file.name;
      $(".dz-secondary").textContent =
        `${(file.size / 1024).toFixed(1)} KB · ready to redact`;
    } else {
      $(".dz-primary").textContent = "Drop a file here";
      $(".dz-secondary").textContent =
        ".txt, .md, source, .pdf, .docx, .eml, .msg · up to 10 MB";
    }
    updateRedactEnabled();
  };

  ["dragenter", "dragover"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.add("drag");
    })
  );
  ["dragleave", "drop"].forEach((ev) =>
    dropzone.addEventListener(ev, (e) => {
      e.preventDefault();
      dropzone.classList.remove("drag");
    })
  );
  dropzone.addEventListener("drop", (e) => {
    if (e.dataTransfer.files.length) setFile(e.dataTransfer.files[0]);
  });
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) setFile(e.target.files[0]);
  });
  pasteText.addEventListener("input", updateRedactEnabled);

  // ----- redact submit -----
  const status = $("#status");
  const result = $("#result");
  const resultText = $("#result-text");
  const resultNote = $("#result-note");
  const downloadResult = $("#download-result");
  const downloadMapping = $("#download-mapping");
  const mappingPreview = $("#mapping-preview");

  const setStatus = (msg, kind = "") => {
    status.textContent = msg;
    status.className = `status ${kind}`;
  };

  const readJsonFile = (file) =>
    new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => {
        try {
          resolve(JSON.parse(r.result));
        } catch (e) {
          reject(e);
        }
      };
      r.onerror = () => reject(r.error);
      r.readAsText(file);
    });

  // The server always returns JSON, but proxies / runtime crashes occasionally
  // produce plain-text bodies. Surface a useful message instead of a JSON
  // parse error.
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
        "[Binary file ready — use the Download button.]";
      downloadResult.href = objectUrl(bytes, json.content_type || "application/octet-stream");
    } else {
      resultText.textContent = json.text;
      downloadResult.href = objectUrl(json.text, "text/plain;charset=utf-8");
    }
    downloadResult.download = json.filename;

    const mappingJson = JSON.stringify(json.mapping || {}, null, 2);
    mappingPreview.textContent = mappingJson;
    downloadMapping.href = objectUrl(mappingJson, "application/json");
    const baseName = (json.filename || "redacted").replace(/\.[^.]+$/, "");
    downloadMapping.download = `${baseName}.mapping.json`;
  };

  redactBtn.addEventListener("click", async () => {
    setStatus("Redacting…");
    redactBtn.disabled = true;
    try {
      const fd = new FormData();
      if (chosenFile) {
        fd.append("file", chosenFile);
      } else {
        fd.append("text", pasteText.value);
      }

      const selected = Array.from($("#entities").selectedOptions).map((o) => o.value);
      if (selected.length) fd.append("entities", JSON.stringify(selected));

      const t = parseFloat($("#threshold").value);
      if (!Number.isNaN(t)) fd.append("threshold", String(t));

      const outputFormat = $("#output-format").value;
      if (outputFormat) fd.append("output_format", outputFormat);

      const mappingFile = $("#load-mapping").files[0];
      if (mappingFile) {
        const obj = await readJsonFile(mappingFile);
        fd.append("load_mapping", JSON.stringify(obj));
      }

      const resp = await fetch("/api/redact", { method: "POST", body: fd });
      const json = await parseResponse(resp);
      showResult(json);
      setStatus("Done.", "ok");
    } catch (err) {
      setStatus(err.message || String(err), "error");
    } finally {
      redactBtn.disabled = false;
      updateRedactEnabled();
    }
  });

  // ----- reverse -----
  const reverseBtn = $("#reverse-btn");
  const reverseStatus = $("#reverse-status");
  const reverseText = $("#reverse-text");
  const reverseMappingInput = $("#reverse-mapping");
  const reverseResult = $("#reverse-result");
  const reverseOutput = $("#reverse-output");

  const updateReverseEnabled = () => {
    reverseBtn.disabled = !reverseText.value.trim() || !reverseMappingInput.files[0];
  };
  reverseText.addEventListener("input", updateReverseEnabled);
  reverseMappingInput.addEventListener("change", updateReverseEnabled);

  reverseBtn.addEventListener("click", async () => {
    reverseStatus.textContent = "Reversing…";
    reverseStatus.className = "status";
    reverseBtn.disabled = true;
    try {
      const mapping = await readJsonFile(reverseMappingInput.files[0]);
      const resp = await fetch("/api/reverse", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: reverseText.value, mapping }),
      });
      const json = await parseResponse(resp);
      reverseResult.classList.remove("hidden");
      reverseOutput.textContent = json.text;
      reverseStatus.textContent = "Done.";
      reverseStatus.className = "status ok";
    } catch (err) {
      reverseStatus.textContent = err.message || String(err);
      reverseStatus.className = "status error";
    } finally {
      updateReverseEnabled();
    }
  });
})();
