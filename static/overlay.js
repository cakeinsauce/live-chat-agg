(function () {
  const params = new URLSearchParams(window.location.search);
  const bg = params.get("bg") || "transparent";
  const limit = parseInt(params.get("limit") || "100", 10);
  const showSource = params.get("showsource") === "1";
  const fontSize = params.get("fontsize");

  document.body.classList.add("bg-" + (["transparent", "dark", "light"].includes(bg) ? bg : "transparent"));
  if (fontSize) {
    document.documentElement.style.setProperty("--fontsize", parseInt(fontSize, 10) + "px");
  }

  const obsLike = params.get("bg") === "transparent" && showSource;
  const chromeHidden = params.get("chrome") === "0" || obsLike;
  const chromeEl = document.getElementById("chrome");
  if (chromeEl && chromeHidden) chromeEl.hidden = true;

  const chat = document.getElementById("chat");
  const statsEl = document.getElementById("stats");
  const pinnedEl = document.getElementById("pinned");
  const giftsEl = document.getElementById("gifts");

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

    const pinBtn = document.createElement("button");
    pinBtn.className = "mod-btn mod-pin";
    pinBtn.textContent = "\uD83D\uDCCC";
    pinBtn.title = "Pin message";
    pinBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      fetch("/api/pin", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: {
            platform: row.dataset.platform,
            user_id:  row.dataset.userId,
            username: row.dataset.username,
            text:     row.dataset.msgText,
            color:    row.dataset.color || undefined,
          },
        }),
      }).catch(() => {});
    });

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
    row.dataset.color    = String(msg.color     || "");

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

    (msg.badges || []).forEach((b) => {
      const badge = document.createElement("span");
      badge.className = "badge";
      badge.textContent = b;
      row.appendChild(badge);
    });

    const name = document.createElement("span");
    name.className = "username " + (msg.platform || "");
    name.textContent = msg.username;
    if (msg.color) name.style.color = msg.color;
    row.appendChild(name);

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
    if (msg.color) name.style.color = msg.color;
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

    const info = document.createElement("div");
    info.className = "gift-info";

    const gName = document.createElement("div");
    gName.className = "gift-name";
    gName.textContent = msg.gift_name || "Gift";
    info.appendChild(gName);

    const gUser = document.createElement("div");
    gUser.className = "gift-user";
    gUser.textContent = msg.username || "";
    info.appendChild(gUser);

    card.appendChild(info);

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

  function makeStatsCol(platform, heading, fields) {
    const col = document.createElement("div");
    col.className = "stats-col " + platform;

    const h = document.createElement("div");
    h.className = "stats-heading";
    h.textContent = heading;
    col.appendChild(h);

    const row = document.createElement("div");
    row.className = "stats-row";

    fields.forEach((field) => {
      const s = document.createElement("div");
      s.className = "stat";
      s.dataset.field = field;

      const val = document.createElement("div");
      val.className = "stat-value";
      val.textContent = "\u2013";
      s.appendChild(val);

      const lbl = document.createElement("div");
      lbl.className = "stat-label";
      lbl.textContent = field;
      s.appendChild(lbl);

      row.appendChild(s);
    });

    col.appendChild(row);
    return col;
  }

  function applyStats(msg) {
    if (!statsEl) return;

    let tiktokCol = statsEl.querySelector(".stats-col.tiktok");
    let twitchCol = statsEl.querySelector(".stats-col.twitch");

    if (!tiktokCol) {
      tiktokCol = makeStatsCol("tiktok", "TikTok", ["viewers", "gifts", "subs", "likes"]);
      statsEl.appendChild(tiktokCol);
    }
    if (!twitchCol) {
      twitchCol = makeStatsCol("twitch", "Twitch", ["viewers", "subs"]);
      statsEl.appendChild(twitchCol);
    }

    const tt = msg.tiktok || {};
    const tw = msg.twitch || {};

    [["viewers", tt.viewers], ["gifts", tt.gifts], ["subs", tt.subs], ["likes", tt.likes]].forEach(([field, value]) => {
      const el = tiktokCol.querySelector('.stat[data-field="' + field + '"] .stat-value');
      if (el) el.textContent = fmtNum(value);
    });

    [["viewers", tw.viewers], ["subs", tw.subs]].forEach(([field, value]) => {
      const el = twitchCol.querySelector('.stat[data-field="' + field + '"] .stat-value');
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
    while (pinnedEl.firstChild) pinnedEl.removeChild(pinnedEl.firstChild);

    const inner = msg.message || {};

    const lbl = document.createElement("div");
    lbl.className = "pinned-label";
    lbl.textContent = "Pinned";
    pinnedEl.appendChild(lbl);

    const row = document.createElement("div");
    row.className = "pinned-row";

    const name = document.createElement("span");
    name.className = "username " + (inner.platform || "");
    name.textContent = inner.username || "";
    if (inner.color) name.style.color = inner.color;
    row.appendChild(name);

    const text = document.createElement("span");
    text.className = "text";
    text.textContent = inner.text || "";
    row.appendChild(text);

    pinnedEl.appendChild(row);
    pinnedEl.hidden = false;
  }

  function applyUnpin() {
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

    inner.appendChild(toggle);
    inner.appendChild(input);
    inner.appendChild(tplBtn);
    inner.appendChild(emojiBtn);
    inner.appendChild(sendBtn);

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

    sendBtn.addEventListener("click", doSend);
    input.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); doSend(); }
    });

    loadTemplates();
  }

  connect();

  try { if (window.ChatTTS && window.ChatTTS.init) window.ChatTTS.init(); } catch (_) {}

  initComposer();
})();
