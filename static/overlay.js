(function () {
  const params = new URLSearchParams(window.location.search);
  const bg = params.get("bg") || "dark";
  const limit = parseInt(params.get("limit") || "100", 10);
  const showSource = params.get("showsource") === "1";
  const fontSize = params.get("fontsize");

  document.body.classList.add("bg-" + (["transparent", "dark", "light"].includes(bg) ? bg : "dark"));
  if (fontSize) {
    document.documentElement.style.setProperty("--fontsize", parseInt(fontSize, 10) + "px");
  }

  const obsLike = params.get("bg") === "transparent" && showSource;
  const chromeHidden = params.get("chrome") === "0" || obsLike;
  if (chromeHidden) document.body.classList.add("chrome-hidden");

  const desktopMode = params.get("desktop") === "1";
  if (desktopMode) document.body.classList.add("desktop");

  const chat = document.getElementById("chat");
  const statsEl = document.getElementById("stats");
  const pinnedEl = document.getElementById("pinned");
  const giftsEl = document.getElementById("gifts");
  const durationEl = document.getElementById("duration");
  const lockBtn = document.getElementById("lock-btn");

  let streamStartedAt = 0;
  let pinHideTimer = null;

  const MAX_GIFTS = 8;
  const giftMap = new Map();

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : s;
    return div.innerHTML;
  }

  function makeDot(platform) {
    const dot = document.createElement("span");
    dot.className = "dot " + platform;
    return dot;
  }

  function fmtNum(n) {
    if (n == null) return "\u2013";
    if (n >= 1000000) return (n / 1000000).toFixed(1) + "M";
    if (n >= 1000) return (n / 1000).toFixed(1) + "K";
    return String(n);
  }

  function appendToChat(row) {
    chat.appendChild(row);
    while (chat.children.length > limit) {
      chat.removeChild(chat.firstChild);
    }
    chat.scrollTop = chat.scrollHeight;
  }

  function addModButtons(row) {
    if (chromeHidden) return;

    const actions = document.createElement("div");
    actions.className = "mod-actions";

    const blockBtn = document.createElement("button");
    blockBtn.className = "mod-btn mod-block";
    blockBtn.textContent = "\u2715";
    blockBtn.title = "Block user";
    blockBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fetch("/api/block", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: row.dataset.platform, user_id: row.dataset.userId }),
      }).catch(() => {});
      row.remove();
    });

    function messagePayload() {
      return {
        platform: row.dataset.platform,
        user_id:  row.dataset.userId,
        username: row.dataset.username,
        text:     row.dataset.msgText,
      };
    }

    const showBtn = document.createElement("button");
    showBtn.className = "mod-btn mod-show";
    showBtn.textContent = "\uD83D\uDCE2";
    showBtn.title = "Show to viewers for 5s";
    showBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fetch("/api/show", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messagePayload() }),
      }).catch(() => {});
    });

    const pinBtn = document.createElement("button");
    pinBtn.className = "mod-btn mod-pin";
    pinBtn.textContent = "\uD83D\uDCCC";
    pinBtn.title = "Pin message (until unpinned)";
    pinBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fetch("/api/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: messagePayload() }),
      }).catch(() => {});
    });

    actions.appendChild(showBtn);
    actions.appendChild(blockBtn);
    actions.appendChild(pinBtn);
    row.appendChild(actions);
  }

  function renderChat(msg) {
    const row = document.createElement("div");
    row.className = "msg " + (msg.platform || "");
    row.dataset.platform = String(msg.platform || "");
    row.dataset.userId   = String(msg.user_id  || "");
    row.dataset.username = String(msg.username  || "");
    row.dataset.msgText  = String(msg.text      || "");

    if (showSource) {
      if (msg.avatar_url) {
        const img = document.createElement("img");
        img.className = "avatar";
        img.src = msg.avatar_url;
        img.referrerPolicy = "no-referrer";
        img.onerror = () => img.replaceWith(makeDot(msg.platform));
        row.appendChild(img);
      } else {
        row.appendChild(makeDot(msg.platform));
      }
    }

    const name = document.createElement("span");
    name.className = "username " + (msg.platform || "");
    name.textContent = msg.username;
    row.appendChild(name);

    const sep = document.createElement("span");
    sep.className = "msg-sep";
    sep.textContent = ":";
    row.appendChild(sep);

    const text = document.createElement("span");
    text.className = "text";
    text.textContent = msg.text == null ? "" : msg.text;
    row.appendChild(text);

    addModButtons(row);
    appendToChat(row);

    try {
      if (window.ChatTTS && window.ChatTTS.speak) window.ChatTTS.speak(msg.text);
    } catch (_) {}
  }

  function renderSub(msg) {
    const row = document.createElement("div");
    row.className = "msg " + (msg.platform || "") + " sub";
    row.dataset.platform = String(msg.platform || "");
    row.dataset.userId = String(msg.user_id || "");

    const name = document.createElement("span");
    name.className = "username " + (msg.platform || "");
    name.textContent = msg.username;
    row.appendChild(name);

    const label = document.createElement("span");
    label.className = "sub-label";
    let labelText = "subscribed";
    if (msg.months && msg.months > 0) labelText += " \xd7 " + msg.months + " mo";
    label.textContent = labelText;
    row.appendChild(label);

    if (msg.text) {
      const text = document.createElement("span");
      text.className = "text";
      text.textContent = msg.text;
      row.appendChild(text);
    }

    appendToChat(row);
  }

  function makeGiftGlyph() {
    const span = document.createElement("span");
    span.className = "gift-glyph";
    span.textContent = "\uD83C\uDF81";
    return span;
  }

  function renderGift(msg) {
    const key = String(msg.user_id || "") + "|" + String(msg.gift_id || msg.gift_name || "");
    const incoming = msg.count || 1;

    if (giftMap.has(key)) {
      const entry = giftMap.get(key);
      entry.count += incoming;
      entry.countEl.textContent = "\xd7" + entry.count;
      return;
    }

    const card = document.createElement("div");
    card.className = "gift";
    card.dataset.platform = String(msg.platform || "");
    card.dataset.userId = String(msg.user_id || "");

    const gUser = document.createElement("span");
    gUser.className = "gift-user";
    gUser.textContent = msg.username || "";
    card.appendChild(gUser);

    const verb = document.createElement("span");
    verb.className = "gift-verb";
    verb.textContent = " \u043e\u0442\u043f\u0440\u0430\u0432\u0438\u043b(-\u0430) \u00ab";
    card.appendChild(verb);

    const gName = document.createElement("span");
    gName.className = "gift-name";
    gName.textContent = msg.gift_name || "Gift";
    card.appendChild(gName);

    const closeQuote = document.createElement("span");
    closeQuote.className = "gift-verb";
    closeQuote.textContent = "\u00bb ";
    card.appendChild(closeQuote);

    if (msg.gift_image) {
      const img = document.createElement("img");
      img.className = "gift-img";
      img.src = msg.gift_image;
      img.referrerPolicy = "no-referrer";
      img.alt = "";
      img.onerror = () => img.replaceWith(makeGiftGlyph());
      card.appendChild(img);
    } else {
      card.appendChild(makeGiftGlyph());
    }

    const countEl = document.createElement("span");
    countEl.className = "gift-count";
    countEl.textContent = "\xd7" + incoming;
    card.appendChild(countEl);

    giftsEl.appendChild(card);
    giftMap.set(key, { node: card, countEl, count: incoming });

    while (giftsEl.children.length > MAX_GIFTS) {
      const oldest = giftsEl.firstChild;
      for (const [k, v] of giftMap) {
        if (v.node === oldest) { giftMap.delete(k); break; }
      }
      giftsEl.removeChild(oldest);
    }
  }

  function makeStatsStrip(platform, fields) {
    const strip = document.createElement("div");
    strip.className = "stats-strip " + platform;

    fields.forEach(({ field, icon }) => {
      const s = document.createElement("span");
      s.className = "stat";
      s.dataset.field = field;

      const ic = document.createElement("span");
      ic.className = "stat-icon";
      ic.textContent = icon;
      s.appendChild(ic);

      const val = document.createElement("span");
      val.className = "stat-value";
      val.textContent = "\u2013";
      s.appendChild(val);

      strip.appendChild(s);
    });

    return strip;
  }

  function applyStats(msg) {
    if (!statsEl) return;

    if (typeof msg.started_at === "number") streamStartedAt = msg.started_at;

    let tiktokStrip = statsEl.querySelector(".stats-strip.tiktok");
    let twitchStrip = statsEl.querySelector(".stats-strip.twitch");

    if (!tiktokStrip) {
      tiktokStrip = makeStatsStrip("tiktok", [
        { field: "viewers", icon: "\uD83D\uDC41" },
        { field: "gifts", icon: "\uD83C\uDF81" },
        { field: "subs", icon: "\u2795" },
        { field: "likes", icon: "\u2764\uFE0F" },
      ]);
      statsEl.appendChild(tiktokStrip);
    }
    if (!twitchStrip) {
      twitchStrip = makeStatsStrip("twitch", [
        { field: "viewers", icon: "\uD83D\uDC41" },
        { field: "subs", icon: "\u2795" },
      ]);
      statsEl.appendChild(twitchStrip);
    }

    const tt = msg.tiktok || {};
    const tw = msg.twitch || {};

    [["viewers", tt.viewers], ["gifts", tt.gifts], ["subs", tt.subs], ["likes", tt.likes]].forEach(([field, value]) => {
      const el = tiktokStrip.querySelector('.stat[data-field="' + field + '"] .stat-value');
      if (el) el.textContent = fmtNum(value);
    });

    [["viewers", tw.viewers], ["subs", tw.subs]].forEach(([field, value]) => {
      const el = twitchStrip.querySelector('.stat[data-field="' + field + '"] .stat-value');
      if (el) el.textContent = fmtNum(value);
    });
  }

  function applyBlock(msg) {
    const platform = String(msg.platform || "");
    const userId = String(msg.user_id || "");

    Array.from(chat.children).forEach((el) => {
      if (el.dataset.platform === platform && el.dataset.userId === userId) {
        el.remove();
      }
    });

    const toDelete = [];
    for (const [key, entry] of giftMap) {
      if (entry.node.dataset.platform === platform && entry.node.dataset.userId === userId) {
        entry.node.remove();
        toDelete.push(key);
      }
    }
    toDelete.forEach((k) => giftMap.delete(k));
  }

  function applyPin(msg) {
    if (!pinnedEl) return;
    if (pinHideTimer) { clearTimeout(pinHideTimer); pinHideTimer = null; }
    while (pinnedEl.firstChild) pinnedEl.removeChild(pinnedEl.firstChild);

    const inner = msg.message || {};
    const autoHide = typeof msg.auto_hide_ms === "number" && msg.auto_hide_ms > 0;

    const lbl = document.createElement("div");
    lbl.className = "pinned-label";
    lbl.textContent = autoHide ? "On screen" : "Pinned";
    pinnedEl.appendChild(lbl);

    const row = document.createElement("div");
    row.className = "pinned-row";

    const name = document.createElement("span");
    name.className = "username " + (inner.platform || "");
    name.textContent = inner.username || "";
    row.appendChild(name);

    const sep = document.createElement("span");
    sep.className = "msg-sep";
    sep.textContent = ":";
    row.appendChild(sep);

    const text = document.createElement("span");
    text.className = "text";
    text.textContent = inner.text || "";
    row.appendChild(text);

    pinnedEl.appendChild(row);
    pinnedEl.hidden = false;

    if (autoHide) {
      pinHideTimer = setTimeout(() => {
        pinnedEl.hidden = true;
        pinHideTimer = null;
      }, msg.auto_hide_ms);
    }
  }

  function applyUnpin() {
    if (pinHideTimer) { clearTimeout(pinHideTimer); pinHideTimer = null; }
    if (pinnedEl) pinnedEl.hidden = true;
  }

  function dispatch(msg) {
    switch (msg.type) {
      case "chat":  renderChat(msg);  break;
      case "sub":   renderSub(msg);   break;
      case "gift":  renderGift(msg);  break;
      case "stats": applyStats(msg);  break;
      case "block": applyBlock(msg);  break;
      case "pin":   applyPin(msg);    break;
      case "unpin": applyUnpin();     break;
    }
  }

  let ws;
  let reconnectDelay = 1000;

  function connect() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(proto + "://" + window.location.host + "/ws");

    ws.onopen = () => {
      reconnectDelay = 1000;
    };
    ws.onmessage = (ev) => {
      try {
        dispatch(JSON.parse(ev.data));
      } catch (e) {
        /* ignore malformed frames */
      }
    };
    ws.onclose = () => {
      setTimeout(connect, reconnectDelay);
      reconnectDelay = Math.min(reconnectDelay * 2, 15000);
    };
    ws.onerror = () => ws.close();
  }

  function initComposer() {
    if (chromeHidden) return;

    document.body.classList.add("has-composer");

    const mount = document.getElementById("composer-mount");
    if (!mount) return;

    let currentPlatform = localStorage.getItem("composer.platform") || "twitch";
    let templates = [];
    let tplOpen = false;
    let emojiOpen = false;
    let sendInFlight = false;
    let testInFlight = false;

    const composer = document.createElement("div");
    composer.className = "composer";

    const inner = document.createElement("div");
    inner.className = "composer-inner";

    const toggle = document.createElement("div");
    toggle.className = "composer-platform-toggle";

    const btnTW = document.createElement("button");
    btnTW.className = "plat-btn";
    btnTW.dataset.plat = "twitch";
    btnTW.textContent = "TW";

    const btnTT = document.createElement("button");
    btnTT.className = "plat-btn";
    btnTT.dataset.plat = "tiktok";
    btnTT.textContent = "TT";

    function setPlatform(p) {
      currentPlatform = p;
      localStorage.setItem("composer.platform", p);
      toggle.dataset.platform = p;
      sendBtn.style.background = p === "tiktok" ? "var(--tiktok)" : "var(--twitch)";
    }

    btnTW.addEventListener("click", () => setPlatform("twitch"));
    btnTT.addEventListener("click", () => setPlatform("tiktok"));
    toggle.appendChild(btnTW);
    toggle.appendChild(btnTT);

    const input = document.createElement("input");
    input.type = "text";
    input.className = "composer-input";
    input.placeholder = "Send a message\u2026";
    input.maxLength = 500;
    input.setAttribute("autocomplete", "off");

    const tplBtn = document.createElement("button");
    tplBtn.className = "composer-btn";
    tplBtn.title = "Templates";
    tplBtn.textContent = "\uD83D\uDCCB";

    const emojiBtn = document.createElement("button");
    emojiBtn.className = "composer-btn";
    emojiBtn.title = "Emoji";
    emojiBtn.textContent = "\uD83D\uDE00";

    const sendBtn = document.createElement("button");
    sendBtn.className = "composer-send";
    sendBtn.textContent = "Send";

    const testBtn = document.createElement("button");
    testBtn.className = "composer-send composer-test";
    testBtn.textContent = "Test";
    testBtn.title = "Inject a test message (no live stream needed)";

    inner.appendChild(toggle);
    inner.appendChild(input);
    inner.appendChild(tplBtn);
    inner.appendChild(emojiBtn);
    inner.appendChild(sendBtn);
    inner.appendChild(testBtn);

    const statusEl = document.createElement("div");
    statusEl.className = "composer-status";
    let statusTimer = null;

    function showStatus(msg, isErr) {
      statusEl.textContent = msg;
      statusEl.className = "composer-status" + (isErr ? " error" : " ok");
      clearTimeout(statusTimer);
      statusTimer = setTimeout(() => {
        statusEl.textContent = "";
        statusEl.className = "composer-status";
      }, 2500);
    }

    const tplPopup = document.createElement("div");
    tplPopup.className = "composer-popup tpl-popup";
    tplPopup.hidden = true;

    const EMOJIS = [
      "\uD83D\uDE00", "\uD83D\uDE02", "\uD83E\uDD79", "\uD83D\uDE0D", "\uD83E\uDD29", "\uD83D\uDE0E",
      "\uD83E\uDD70", "\uD83D\uDE05", "\uD83E\uDD23", "\uD83D\uDE2D", "\uD83D\uDE24", "\uD83E\uDD14",
      "\uD83D\uDE34", "\uD83E\uDD71", "\uD83C\uDF89", "\uD83D\uDD25", "\uD83D\uDCAF", "\uD83D\uDC4D",
      "\uD83D\uDC4E", "\u2764\uFE0F", "\uD83D\uDC80", "\uD83D\uDE4F", "\uD83E\uDEB6", "\uD83D\uDCAA",
      "\uD83D\uDC40", "\uD83E\uDEE0", "\uD83E\uDD21", "\uD83D\uDCA9", "\uD83C\uDF1A", "\u2B50",
    ];

    const emojiPopup = document.createElement("div");
    emojiPopup.className = "composer-popup emoji-popup";
    emojiPopup.hidden = true;

    EMOJIS.forEach((em) => {
      const btn = document.createElement("button");
      btn.className = "emoji-item";
      btn.textContent = em;
      btn.setAttribute("aria-label", em);
      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        insertAtCursor(input, em);
        closeAll();
        input.focus();
      });
      emojiPopup.appendChild(btn);
    });

    composer.appendChild(inner);
    composer.appendChild(statusEl);
    composer.appendChild(tplPopup);
    composer.appendChild(emojiPopup);
    mount.appendChild(composer);

    setPlatform(currentPlatform);

    function insertAtCursor(field, text) {
      const start = field.selectionStart;
      const end   = field.selectionEnd;
      const val   = field.value;
      field.value = val.slice(0, start) + text + val.slice(end);
      const pos = start + text.length;
      field.setSelectionRange(pos, pos);
    }

    function closeAll() {
      tplPopup.hidden  = true;
      emojiPopup.hidden = true;
      tplOpen   = false;
      emojiOpen = false;
    }

    function renderTemplates() {
      while (tplPopup.firstChild) tplPopup.removeChild(tplPopup.firstChild);
      if (!templates.length) {
        const empty = document.createElement("div");
        empty.className = "tpl-empty";
        empty.textContent = "No templates configured.";
        tplPopup.appendChild(empty);
        return;
      }
      templates.forEach((t) => {
        const item = document.createElement("button");
        item.className = "tpl-item";
        item.textContent = String(t);
        item.addEventListener("click", (e) => {
          e.stopPropagation();
          insertAtCursor(input, String(t));
          closeAll();
          input.focus();
        });
        tplPopup.appendChild(item);
      });
    }

    function loadTemplates() {
      return fetch("/api/settings")
        .then((r) => r.ok ? r.json() : {})
        .then((data) => { templates = Array.isArray(data.templates) ? data.templates : []; })
        .catch(() => { templates = []; });
    }

    tplBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (tplOpen) { closeAll(); return; }
      closeAll();
      tplPopup.hidden = false;
      tplOpen = true;
      renderTemplates();
      loadTemplates().then(renderTemplates).catch(() => {});
    });

    emojiBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      if (emojiOpen) { closeAll(); return; }
      closeAll();
      emojiPopup.hidden = false;
      emojiOpen = true;
    });

    tplPopup.addEventListener("click",   (e) => e.stopPropagation());
    emojiPopup.addEventListener("click", (e) => e.stopPropagation());
    document.addEventListener("click", closeAll);

    function doSend() {
      const text = input.value.trim();
      if (!text || sendInFlight) return;
      sendInFlight = true;
      sendBtn.disabled = true;

      fetch("/api/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: currentPlatform, text }),
      })
        .then((r) => {
          if (!r.ok) return r.text().then((t) => { throw new Error(t || String(r.status)); });
          return r.text();
        })
        .then(() => {
          input.value = "";
          showStatus("Sent!", false);
        })
        .catch((err) => {
          showStatus(err && err.message ? err.message : "Error", true);
        })
        .finally(() => {
          sendInFlight = false;
          sendBtn.disabled = false;
        });
    }

    function doTest() {
      const text = input.value.trim();
      if (!text || testInFlight) return;
      testInFlight = true;
      testBtn.disabled = true;

      fetch("/api/test-message", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: currentPlatform, text, username: "" }),
      })
        .then((r) => {
          if (!r.ok) return r.text().then((t) => { throw new Error(t || String(r.status)); });
          return r.text();
        })
        .then(() => {
          input.value = "";
          showStatus("Test sent!", false);
        })
        .catch((err) => {
          showStatus(err && err.message ? err.message : "Error", true);
        })
        .finally(() => {
          testInFlight = false;
          testBtn.disabled = false;
        });
    }

    sendBtn.addEventListener("click", doSend);
    testBtn.addEventListener("click", doTest);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
    });

    loadTemplates();
  }

  function fmtDuration(totalSec) {
    if (totalSec < 0) totalSec = 0;
    const h = Math.floor(totalSec / 3600);
    const m = Math.floor((totalSec % 3600) / 60);
    const s = Math.floor(totalSec % 60);
    const pad = (n) => String(n).padStart(2, "0");
    return h + ":" + pad(m) + ":" + pad(s);
  }

  function tickDuration() {
    if (!durationEl) return;
    if (!streamStartedAt) {
      durationEl.textContent = "0:00:00";
      return;
    }
    durationEl.textContent = fmtDuration(Date.now() / 1000 - streamStartedAt);
  }

  function initLock() {
    if (!lockBtn) return;
    function apply(locked) {
      document.body.classList.toggle("locked", locked);
      lockBtn.textContent = locked ? "\uD83D\uDD12" : "\uD83D\uDD13";
      lockBtn.title = locked ? "Unlock overlay" : "Lock overlay";
      if (desktopMode) {
        location.hash = (locked ? "lock-" : "unlock-") + Date.now();
      }
    }
    apply(localStorage.getItem("overlay.locked") === "1");
    lockBtn.addEventListener("click", () => {
      const next = !document.body.classList.contains("locked");
      localStorage.setItem("overlay.locked", next ? "1" : "0");
      apply(next);
    });
  }

  function initCloseButton() {
    const btn = document.getElementById("close-btn");
    if (!btn || !desktopMode) return;
    btn.hidden = false;
    btn.addEventListener("click", () => {
      location.hash = "close-" + Date.now();
    });
  }

  function initPopoutButton() {
    const btn = document.getElementById("popout-btn");
    if (!btn || desktopMode) return;
    async function refresh() {
      try {
        const r = await fetch("/api/desktop/available");
        if (!r.ok) return;
        const j = await r.json();
        btn.hidden = !(j.available && !j.running);
      } catch (_) {}
    }
    btn.addEventListener("click", async () => {
      btn.disabled = true;
      try { await fetch("/api/desktop/spawn", { method: "POST" }); } catch (_) {}
      btn.disabled = false;
      refresh();
    });
    refresh();
    setInterval(refresh, 3000);
  }

  function initOpacity() {
    const slider = document.getElementById("opacity-slider");
    if (!slider) return;
    const saved = parseInt(localStorage.getItem("overlay.panel_alpha") || "", 10);
    const initial = Number.isFinite(saved) && saved >= 20 && saved <= 100 ? saved : 85;
    function apply(percent) {
      const clamped = Math.max(20, Math.min(100, percent));
      document.documentElement.style.setProperty("--panel-alpha", (clamped / 100).toFixed(3));
      slider.value = String(clamped);
    }
    apply(initial);
    slider.addEventListener("input", () => {
      const val = parseInt(slider.value, 10);
      if (!Number.isFinite(val)) return;
      apply(val);
      localStorage.setItem("overlay.panel_alpha", String(val));
    });
  }

  connect();

  try { if (window.ChatTTS && window.ChatTTS.init) window.ChatTTS.init(); } catch (_) {}

  initComposer();
  initLock();
  initOpacity();
  initCloseButton();
  initPopoutButton();
  tickDuration();
  setInterval(tickDuration, 1000);
})();
