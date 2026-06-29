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

  const chat = document.getElementById("chat");

  function escapeHtml(s) {
    const div = document.createElement("div");
    div.textContent = s == null ? "" : s;
    return div.innerHTML;
  }

  function render(msg) {
    const row = document.createElement("div");
    row.className = "msg " + msg.platform;

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
    name.className = "username " + msg.platform;
    name.textContent = msg.username;
    if (msg.color) name.style.color = msg.color;
    row.appendChild(name);

    const text = document.createElement("span");
    text.className = "text";
    text.innerHTML = escapeHtml(msg.text);
    row.appendChild(text);

    chat.appendChild(row);

    while (chat.children.length > limit) {
      chat.removeChild(chat.firstChild);
    }
    chat.scrollTop = chat.scrollHeight;
  }

  function makeDot(platform) {
    const dot = document.createElement("span");
    dot.className = "dot " + platform;
    return dot;
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
        render(JSON.parse(ev.data));
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

  connect();
})();
