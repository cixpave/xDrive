/* xDrive — offline AI terminal (frontend) */
"use strict";

const $ = (id) => document.getElementById(id);

const els = {
  chat: $("chat"),
  messages: $("messages"),
  welcome: $("welcome"),
  offlineNote: $("offline-note"),
  input: $("input"),
  send: $("btn-send"),
  convList: $("conv-list"),
  modelSelect: $("model-select"),
  agentMode: $("agent-mode"),
  statusDot: $("status-dot"),
  statusText: $("status-text"),
  streamState: $("stream-state"),
  activity: $("activity"),
};

const state = {
  conversationId: null,
  streaming: false,
  abort: null,
  online: false,
  bootedAt: Date.now(),
};

marked.setOptions({ breaks: true, gfm: true });

/* ───────── clock / uptime ───────── */

function tickClock() {
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  $("clock").textContent =
    `${pad(now.getHours())}:${pad(now.getMinutes())}:${pad(now.getSeconds())}`;
  $("sys-date").textContent =
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const up = Math.floor((Date.now() - state.bootedAt) / 1000);
  $("sys-uptime").textContent =
    `${pad(Math.floor(up / 3600))}:${pad(Math.floor((up % 3600) / 60))}:${pad(up % 60)}`;
}

/* ───────── activity log ───────── */

function logActivity(text, dim = false) {
  const line = document.createElement("div");
  line.className = "act-line" + (dim ? " dim" : "");
  const now = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  const time = document.createElement("span");
  time.className = "act-time";
  time.textContent = `${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}`;
  line.append(time, document.createTextNode(text));
  els.activity.append(line);
  while (els.activity.children.length > 200) els.activity.firstChild.remove();
  els.activity.scrollTop = els.activity.scrollHeight;
}

/* ───────── markdown rendering ───────── */

function renderMarkdown(text) {
  const html = marked.parse(text ?? "");
  const tpl = document.createElement("template");
  tpl.innerHTML = html;
  // strip anything dangerous — local app, but models emit arbitrary text
  tpl.content.querySelectorAll("script, iframe, object, embed").forEach((n) => n.remove());
  tpl.content.querySelectorAll("*").forEach((n) => {
    [...n.attributes].forEach((a) => {
      if (a.name.startsWith("on")) n.removeAttribute(a.name);
    });
  });
  // wrap code blocks with header + copy button
  tpl.content.querySelectorAll("pre > code").forEach((code) => {
    const pre = code.parentElement;
    const lang = ([...code.classList].find((c) => c.startsWith("language-")) || "language-text").slice(9);
    try { hljs.highlightElement(code); } catch (_) { /* unknown language */ }
    const wrap = document.createElement("div");
    wrap.className = "codeblock";
    const head = document.createElement("div");
    head.className = "codeblock-head";
    const label = document.createElement("span");
    label.textContent = lang;
    const copy = document.createElement("button");
    copy.className = "copy-btn";
    copy.textContent = "COPY";
    copy.addEventListener("click", () => {
      navigator.clipboard.writeText(code.textContent).then(() => {
        copy.textContent = "COPIED";
        setTimeout(() => (copy.textContent = "COPY"), 1400);
      });
    });
    head.append(label, copy);
    pre.replaceWith(wrap);
    wrap.append(head, pre);
  });
  return tpl.content;
}

/* ───────── message DOM ───────── */

function addUserMessage(text) {
  const msg = document.createElement("div");
  msg.className = "msg user";
  const line = document.createElement("div");
  line.className = "u-line";
  line.textContent = text;
  msg.append(line);
  els.messages.append(msg);
  scrollToBottom();
}

function addAssistantShell() {
  const msg = document.createElement("div");
  msg.className = "msg assistant";
  const head = document.createElement("div");
  head.className = "msg-head";
  head.textContent = "xDRIVE";
  const content = document.createElement("div");
  content.className = "content";
  msg.append(head, content);
  els.messages.append(msg);
  scrollToBottom();
  return msg;
}

function addToolCard(container, name, args) {
  const card = document.createElement("details");
  card.className = "tool-card";
  const summary = document.createElement("summary");
  summary.textContent = args
    ? `${name} ${JSON.stringify(args).slice(0, 110)}`
    : name;
  const pre = document.createElement("pre");
  pre.textContent = "running…";
  card.append(summary, pre);
  container.append(card);
  scrollToBottom();
  return pre;
}

function addError(container, text) {
  const div = document.createElement("div");
  div.className = "error-note";
  div.textContent = text;
  container.append(div);
  scrollToBottom();
}

function scrollToBottom() {
  els.chat.scrollTop = els.chat.scrollHeight;
}

function nearBottom() {
  return els.chat.scrollHeight - els.chat.scrollTop - els.chat.clientHeight < 120;
}

function setStreamState(live) {
  els.streamState.textContent = live ? "▓ STREAMING" : "IDLE";
  els.streamState.classList.toggle("live", live);
}

/* ───────── status / models ───────── */

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const s = await res.json();
    const wasOnline = state.online;
    state.online = s.online;
    els.statusDot.className = "status-dot " + (s.online ? "on" : "off");
    els.statusText.textContent = s.online ? "UP" : "DOWN";
    $("sys-backend").textContent = s.online ? s.backend_kind.toUpperCase() : "NONE";
    $("sys-models").textContent = s.models.length;
    $("net-state").textContent = s.online ? "AIR·GAPPED" : "NO RUNTIME";
    $("net-state").className = s.online ? "on" : "";
    $("boot-runtime").textContent = s.online
      ? `> runtime online: ${s.backend_kind} · ${s.models.length} model(s) loaded`
      : "> no LLM runtime found — start ollama or llama-server";
    els.offlineNote.hidden = s.online;
    $("ws-path").textContent = s.workspace || "—";
    $("set-workspace").textContent = s.workspace || "";
    $("bar-port").textContent = location.host;

    const current = els.modelSelect.value;
    els.modelSelect.innerHTML = "";
    for (const m of s.models) {
      const opt = document.createElement("option");
      opt.value = m;
      opt.textContent = m;
      els.modelSelect.append(opt);
    }
    if (s.models.includes(current)) els.modelSelect.value = current;
    else if (s.default_model && s.models.includes(s.default_model)) {
      els.modelSelect.value = s.default_model;
    }
    updateModelReadouts();
    if (s.online && !wasOnline) logActivity(`runtime up: ${s.backend_kind}`);
    if (!s.online && wasOnline) logActivity("runtime down", true);
  } catch (_) {
    els.statusDot.className = "status-dot off";
    els.statusText.textContent = "ERR";
  }
}

function updateModelReadouts() {
  const m = els.modelSelect.value || "NO MODEL";
  $("top-model").textContent = m.toUpperCase();
  $("bar-model").textContent = m;
}

/* ───────── conversations ───────── */

async function refreshConversations() {
  const res = await fetch("/api/conversations");
  const items = await res.json();
  els.convList.innerHTML = "";
  for (const c of items) {
    const row = document.createElement("div");
    row.className = "conv-item" + (c.id === state.conversationId ? " active" : "");
    const title = document.createElement("span");
    title.className = "conv-title";
    title.textContent = c.title || "untitled";
    const del = document.createElement("button");
    del.className = "conv-del";
    del.textContent = "✕";
    del.title = "Delete session";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
      logActivity(`session deleted: ${c.id}`, true);
      if (c.id === state.conversationId) newChat();
      refreshConversations();
    });
    row.append(title, del);
    row.addEventListener("click", () => openConversation(c.id));
    els.convList.append(row);
  }
}

async function openConversation(id) {
  const res = await fetch(`/api/conversations/${id}`);
  if (!res.ok) return;
  const conv = await res.json();
  state.conversationId = conv.id;
  els.welcome.hidden = true;
  els.messages.innerHTML = "";
  let currentShell = null;
  for (const m of conv.messages) {
    if (m.role === "user") {
      addUserMessage(m.content);
      currentShell = null;
    } else if (m.role === "assistant") {
      if (!currentShell) currentShell = addAssistantShell();
      currentShell.querySelector(".content").append(renderMarkdown(m.content));
    } else if (m.role === "tool") {
      if (!currentShell) currentShell = addAssistantShell();
      const idx = m.content.indexOf(" -> ");
      const pre = addToolCard(currentShell.querySelector(".content"), m.tool || "tool", null);
      pre.textContent = idx >= 0 ? m.content.slice(idx + 4) : m.content;
    }
  }
  refreshConversations();
  scrollToBottom();
}

function newChat() {
  state.conversationId = null;
  els.messages.innerHTML = "";
  els.welcome.hidden = false;
  els.input.focus();
  refreshConversations();
}

/* ───────── chat streaming ───────── */

async function sendMessage() {
  const text = els.input.value.trim();
  if (!text || state.streaming) return;

  els.input.value = "";
  autosize();
  els.welcome.hidden = true;
  addUserMessage(text);

  const shell = addAssistantShell();
  const content = shell.querySelector(".content");
  let streamedText = "";
  let liveBlock = null; // element re-rendered as tokens arrive

  const startLiveBlock = () => {
    liveBlock = document.createElement("div");
    content.append(liveBlock);
    streamedText = "";
  };
  startLiveBlock();

  const renderLive = (final = false) => {
    const stick = nearBottom();
    liveBlock.innerHTML = "";
    liveBlock.append(renderMarkdown(streamedText));
    if (!final) {
      const cur = document.createElement("span");
      cur.className = "cursor-blink";
      (liveBlock.lastElementChild || liveBlock).append(cur);
    }
    if (stick) scrollToBottom();
  };

  state.streaming = true;
  setSendButton(true);
  setStreamState(true);
  logActivity(`query sent (${els.agentMode.checked ? "agent" : "chat"})`);
  const controller = new AbortController();
  state.abort = controller;

  let renderTimer = null;
  const scheduleRender = () => {
    if (renderTimer) return;
    renderTimer = setTimeout(() => { renderTimer = null; renderLive(); }, 80);
  };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        conversation_id: state.conversationId,
        message: text,
        model: els.modelSelect.value || undefined,
        agent_mode: els.agentMode.checked,
      }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      addError(content, err.error || `request failed (${res.status})`);
      return;
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    let toolPre = null;

    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      let idx;
      while ((idx = buffer.indexOf("\n\n")) >= 0) {
        const frame = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        if (!frame.startsWith("data:")) continue;
        let ev;
        try { ev = JSON.parse(frame.slice(5)); } catch (_) { continue; }

        if (ev.type === "meta") {
          state.conversationId = ev.conversation_id;
        } else if (ev.type === "token") {
          streamedText += ev.text;
          scheduleRender();
        } else if (ev.type === "tool_call") {
          renderLive(true);
          toolPre = addToolCard(content, ev.name, ev.args);
          logActivity(`tool: ${ev.name}`);
          startLiveBlock();
        } else if (ev.type === "tool_result") {
          if (toolPre) toolPre.textContent = ev.output;
          logActivity(`tool done: ${ev.name}`, true);
          scrollToBottom();
        } else if (ev.type === "error") {
          renderLive(true);
          addError(content, ev.message);
          logActivity(`error: ${ev.message}`, true);
        } else if (ev.type === "done") {
          break;
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") addError(content, `connection lost: ${err.message}`);
    else logActivity("stream aborted by user", true);
  } finally {
    if (renderTimer) clearTimeout(renderTimer);
    renderLive(true);
    state.streaming = false;
    state.abort = null;
    setSendButton(false);
    setStreamState(false);
    logActivity("response complete", true);
    refreshConversations();
    els.input.focus();
  }
}

function setSendButton(streaming) {
  els.send.textContent = streaming ? "ABORT" : "EXEC";
  els.send.classList.toggle("stop", streaming);
  els.send.title = streaming ? "Abort stream" : "Send [Enter]";
}

/* ───────── settings ───────── */

async function openSettings() {
  const cfg = await (await fetch("/api/config")).json();
  $("set-backend").value = cfg.backend_url ?? "auto";
  $("set-model").value = cfg.default_model ?? "";
  $("set-temp").value = cfg.temperature ?? 0.7;
  $("set-system").value = cfg.system_prompt ?? "";
  $("settings-modal").hidden = false;
}

async function saveSettings() {
  await fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      backend_url: $("set-backend").value.trim() || "auto",
      default_model: $("set-model").value.trim(),
      temperature: parseFloat($("set-temp").value) || 0.7,
      system_prompt: $("set-system").value,
    }),
  });
  $("settings-modal").hidden = true;
  logActivity("config written");
  refreshStatus();
}

/* ───────── theme ───────── */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("xdrive-theme", theme);
}

/* ───────── input behavior ───────── */

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 200) + "px";
}

/* ───────── wire-up ───────── */

els.send.addEventListener("click", () => {
  if (state.streaming) state.abort?.abort();
  else sendMessage();
});
els.input.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});
els.input.addEventListener("input", autosize);
els.modelSelect.addEventListener("change", () => {
  updateModelReadouts();
  logActivity(`model set: ${els.modelSelect.value}`, true);
});
els.agentMode.addEventListener("change", () => {
  logActivity(`agent mode ${els.agentMode.checked ? "ENABLED" : "disabled"}`);
});

$("btn-new").addEventListener("click", newChat);
$("btn-theme").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
$("btn-settings").addEventListener("click", openSettings);
$("btn-close-settings").addEventListener("click", () => ($("settings-modal").hidden = true));
$("btn-save-settings").addEventListener("click", saveSettings);
$("settings-modal").addEventListener("click", (e) => {
  if (e.target === $("settings-modal")) $("settings-modal").hidden = true;
});
document.querySelector(".sys .kv:last-child").addEventListener("click", () => {
  logActivity("rescanning runtime…", true);
  refreshStatus();
});
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    els.input.value = chip.dataset.fill.replaceAll("\\n", "\n");
    autosize();
    els.input.focus();
  });
});

applyTheme(localStorage.getItem("xdrive-theme") || "dark");
tickClock();
setInterval(tickClock, 1000);
refreshStatus();
refreshConversations();
setInterval(refreshStatus, 20000);
logActivity("xDrive terminal ready");
els.input.focus();
