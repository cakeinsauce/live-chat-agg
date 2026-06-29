(function () {
  const form = document.getElementById("settings-form");
  const status = document.getElementById("status");
  const saveBtn = document.getElementById("save-btn");
  const reconnectBtn = document.getElementById("reconnect-btn");
  const copyObsBtn = document.getElementById("copy-obs-btn");
  const obsUrlEl = document.getElementById("obs-url");

  const fields = [
    "twitch_channel",
    "tiktok_username",
    "sign_api_key",
    "twitch_oauth_token",
    "twitch_bot_username",
    "twitch_client_id",
    "twitch_client_secret",
    "tiktok_sessionid",
    "tiktok_target_idc",
  ];

  const ttsEnabledEl = document.getElementById("tts_enabled");
  const ttsVoiceEl = document.getElementById("tts_voice");
  const ttsVoiceHint = document.getElementById("tts-voice-hint");

  let savedTtsVoice = "";

  const templateListEl = document.getElementById("template-list");
  const templateInputEl = document.getElementById("template-input");
  const templateAddBtn = document.getElementById("template-add-btn");
  let templates = [];

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

  function populateVoices() {
    if (!window.speechSynthesis) return;

    const voices = window.speechSynthesis.getVoices();
    const ruVoices = voices.filter(function (v) { return v.lang.startsWith("ru"); });

    while (ttsVoiceEl.firstChild) {
      ttsVoiceEl.removeChild(ttsVoiceEl.firstChild);
    }

    var autoOpt = document.createElement("option");
    autoOpt.value = "";
    autoOpt.textContent = "Auto (first Russian voice)";
    ttsVoiceEl.appendChild(autoOpt);

    if (ruVoices.length === 0) {
      ttsVoiceEl.disabled = true;
      ttsVoiceHint.textContent =
        "No Russian voices found on this system. On macOS go to System Settings → Accessibility → Spoken Content → Manage Voices and add Russian (Milena). On Windows: Settings → Time & Language → Speech → Manage voices.";
      ttsVoiceHint.classList.add("warn");
    } else {
      ttsVoiceEl.disabled = false;
      ttsVoiceHint.textContent =
        "Voices come from your operating system. On macOS enable 'Milena' (Russian) in System Settings → Accessibility → Spoken Content. On Windows install a Russian voice in Settings → Time & Language → Speech.";
      ttsVoiceHint.classList.remove("warn");

      ruVoices.forEach(function (v) {
        var opt = document.createElement("option");
        opt.value = v.name;
        opt.textContent = v.name + " (" + v.lang + ")";
        ttsVoiceEl.appendChild(opt);
      });
    }

    if (savedTtsVoice) {
      var found = false;
      var opts = ttsVoiceEl.options;
      for (var i = 0; i < opts.length; i++) {
        if (opts[i].value === savedTtsVoice) { found = true; break; }
      }
      if (!found) {
        var ghost = document.createElement("option");
        ghost.value = savedTtsVoice;
        ghost.textContent = savedTtsVoice + " (not installed)";
        ttsVoiceEl.appendChild(ghost);
      }
      ttsVoiceEl.value = savedTtsVoice;
    }
  }

  if (window.speechSynthesis) {
    window.speechSynthesis.onvoiceschanged = populateVoices;
    populateVoices(); // Firefox already has voices; Chrome populates them asynchronously
  } else {
    ttsVoiceEl.disabled = true;
    var unavailOpt = document.createElement("option");
    unavailOpt.value = "";
    unavailOpt.textContent = "Speech synthesis not available in this browser";
    ttsVoiceEl.appendChild(unavailOpt);
  }

  function renderTemplates() {
    while (templateListEl.firstChild) {
      templateListEl.removeChild(templateListEl.firstChild);
    }
    templates.forEach(function (text, idx) {
      var li = document.createElement("li");
      li.className = "template-row";

      var span = document.createElement("span");
      span.className = "template-text";
      span.textContent = text;

      var removeBtn = document.createElement("button");
      removeBtn.type = "button";
      removeBtn.className = "btn ghost";
      removeBtn.textContent = "Remove";
      (function (i) {
        removeBtn.addEventListener("click", function () {
          templates.splice(i, 1);
          renderTemplates();
        });
      })(idx);

      li.appendChild(span);
      li.appendChild(removeBtn);
      templateListEl.appendChild(li);
    });
  }

  templateAddBtn.addEventListener("click", function () {
    var val = templateInputEl.value.trim();
    if (!val) return;
    templates.push(val);
    templateInputEl.value = "";
    renderTemplates();
  });

  templateInputEl.addEventListener("keydown", function (e) {
    if (e.key === "Enter") {
      e.preventDefault();
      templateAddBtn.click();
    }
  });

  function fillForm(data) {
    fields.forEach(function (k) {
      var el = document.getElementById(k);
      if (el) el.value = data[k] || "";
    });

    ttsEnabledEl.checked = !!data.tts_enabled;

    savedTtsVoice = data.tts_voice || "";
    populateVoices();

    templates = Array.isArray(data.templates) ? data.templates.slice() : [];
    renderTemplates();
  }

  function readForm() {
    var out = {};
    fields.forEach(function (k) {
      var el = document.getElementById(k);
      out[k] = el ? el.value.trim() : "";
    });

    out.tts_enabled = ttsEnabledEl.checked;
    out.tts_voice = ttsVoiceEl.value;
    out.templates = templates.slice();

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
        "Saved! Reconnected " +
          (data.connectors || 0) +
          " source" +
          (data.connectors === 1 ? "" : "s") +
          summary,
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
