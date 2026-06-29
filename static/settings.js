(function () {
  const form = document.getElementById("settings-form");
  const status = document.getElementById("status");
  const saveBtn = document.getElementById("save-btn");
  const reconnectBtn = document.getElementById("reconnect-btn");
  const copyObsBtn = document.getElementById("copy-obs-btn");
  const obsUrlEl = document.getElementById("obs-url");

  const fields = ["twitch_channel", "tiktok_username", "sign_api_key"];

  function setStatus(text, kind) {
    status.textContent = text;
    status.className = "status visible " + (kind || "");
    if (kind === "success") {
      setTimeout(() => {
        if (status.textContent === text) {
          status.className = "status";
        }
      }, 3500);
    }
  }

  function setBusy(busy) {
    saveBtn.disabled = busy;
    reconnectBtn.disabled = busy;
    saveBtn.textContent = busy ? "Saving…" : "Save & connect";
  }

  function fillForm(data) {
    fields.forEach((k) => {
      const el = document.getElementById(k);
      if (el) el.value = data[k] || "";
    });
  }

  function readForm() {
    const out = {};
    fields.forEach((k) => {
      const el = document.getElementById(k);
      out[k] = el ? el.value.trim() : "";
    });
    return out;
  }

  async function loadSettings() {
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      fillForm(data);
      if (!data.persistent) {
        setStatus(
          "This server can't save settings (no writable config dir). Use .env instead.",
          "error",
        );
      }
    } catch (err) {
      setStatus("Could not load current settings: " + err.message, "error");
    }
  }

  async function saveSettings(ev) {
    ev.preventDefault();
    setBusy(true);
    const body = readForm();
    try {
      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      if (!res.ok) {
        const detail = await res.text();
        throw new Error(detail || "HTTP " + res.status);
      }
      const data = await res.json();
      fillForm(data);
      const sources = [];
      if (data.twitch_channel) sources.push("Twitch: " + data.twitch_channel);
      if (data.tiktok_username) sources.push("TikTok: " + data.tiktok_username);
      const summary = sources.length ? " (" + sources.join(", ") + ")" : "";
      setStatus(
        "Saved! Reconnected " + (data.connectors || 0) + " source" + (data.connectors === 1 ? "" : "s") + summary,
        "success",
      );
    } catch (err) {
      setStatus("Save failed: " + err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  async function reconnect() {
    setBusy(true);
    try {
      const res = await fetch("/api/reconnect", { method: "POST" });
      if (!res.ok) throw new Error("HTTP " + res.status);
      const data = await res.json();
      setStatus("Reconnected " + (data.connectors || 0) + " source(s).", "success");
    } catch (err) {
      setStatus("Reconnect failed: " + err.message, "error");
    } finally {
      setBusy(false);
    }
  }

  function setObsUrl() {
    const base = window.location.origin + "/?bg=transparent&showsource=1";
    obsUrlEl.textContent = base;
    return base;
  }

  async function copyObs() {
    const url = setObsUrl();
    try {
      await navigator.clipboard.writeText(url);
      setStatus("Copied OBS URL to clipboard.", "success");
    } catch {
      setStatus("Copy failed. Select the URL above manually and copy it.", "error");
    }
  }

  form.addEventListener("submit", saveSettings);
  reconnectBtn.addEventListener("click", reconnect);
  copyObsBtn.addEventListener("click", copyObs);

  setObsUrl();
  loadSettings();
})();
