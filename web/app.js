/* Ember — offline AI assistant (frontend) */
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
  sidebar: $("sidebar"),
};

const state = {
  conversationId: null,
  streaming: false,
  abort: null,
  online: false,
};

marked.setOptions({ breaks: true, gfm: true });

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
    copy.textContent = "copy";
    copy.addEventListener("click", () => {
      navigator.clipboard.writeText(code.textContent).then(() => {
        copy.textContent = "copied!";
        setTimeout(() => (copy.textContent = "copy"), 1400);
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
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  msg.append(bubble);
  els.messages.append(msg);
  scrollToBottom();
}

function addAssistantShell() {
  const msg = document.createElement("div");
  msg.className = "msg assistant";
  const head = document.createElement("div");
  head.className = "msg-head";
  head.innerHTML = `<span class="dot"></span> EMBER`;
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
  summary.textContent = `${name} ${JSON.stringify(args ?? {}).slice(0, 120)}`;
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

/* ───────── status / models ───────── */

async function refreshStatus() {
  try {
    const res = await fetch("/api/status");
    const s = await res.json();
    state.online = s.online;
    els.statusDot.className = "status-dot " + (s.online ? "on" : "off");
    els.statusText.textContent = s.online
      ? `${s.backend_kind} · ${s.models.length} model(s)`
      : "no model runtime";
    els.offlineNote.hidden = s.online;
    $("set-workspace").textContent = s.workspace || "";
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
  } catch (_) {
    els.statusDot.className = "status-dot off";
    els.statusText.textContent = "server unreachable";
  }
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
    title.textContent = c.title || "Untitled";
    const del = document.createElement("button");
    del.className = "conv-del";
    del.textContent = "✕";
    del.title = "Delete conversation";
    del.addEventListener("click", async (e) => {
      e.stopPropagation();
      await fetch(`/api/conversations/${c.id}`, { method: "DELETE" });
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
      addError(content, err.error || `Request failed (${res.status})`);
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
          startLiveBlock();
        } else if (ev.type === "tool_result") {
          if (toolPre) toolPre.textContent = ev.output;
          scrollToBottom();
        } else if (ev.type === "error") {
          renderLive(true);
          addError(content, ev.message);
        } else if (ev.type === "done") {
          break;
        }
      }
    }
  } catch (err) {
    if (err.name !== "AbortError") addError(content, `Connection lost: ${err.message}`);
  } finally {
    if (renderTimer) clearTimeout(renderTimer);
    renderLive(true);
    state.streaming = false;
    state.abort = null;
    setSendButton(false);
    refreshConversations();
    els.input.focus();
  }
}

function setSendButton(streaming) {
  if (streaming) {
    els.send.classList.add("stop");
    els.send.title = "Stop";
    els.send.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14"><rect x="5" y="5" width="14" height="14" rx="2" fill="currentColor"/></svg>`;
  } else {
    els.send.classList.remove("stop");
    els.send.title = "Send";
    els.send.innerHTML = `<svg viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M3.4 20.4 22 12 3.4 3.6 3.4 10l13 2-13 2z"/></svg>`;
  }
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
  refreshStatus();
}

/* ───────── theme ───────── */

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("ember-theme", theme);
}

/* ───────── input behavior ───────── */

function autosize() {
  els.input.style.height = "auto";
  els.input.style.height = Math.min(els.input.scrollHeight, 220) + "px";
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
$("btn-collapse").addEventListener("click", () => {
  els.sidebar.classList.add("collapsed");
  $("btn-expand").hidden = false;
});
$("btn-expand").addEventListener("click", () => {
  els.sidebar.classList.remove("collapsed");
  $("btn-expand").hidden = true;
});
document.querySelector(".status-row").addEventListener("click", refreshStatus);
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => {
    els.input.value = chip.dataset.fill.replaceAll("\\n", "\n");
    autosize();
    els.input.focus();
  });
});

applyTheme(localStorage.getItem("ember-theme") || "dark");
refreshStatus();
refreshConversations();
setInterval(refreshStatus, 20000);
els.input.focus();
