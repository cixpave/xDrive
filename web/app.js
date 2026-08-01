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
  researchMode: $("research-mode"),
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
  const h24 = now.getHours();
  const h12 = h24 % 12 || 12;
  const ampm = h24 < 12 ? "AM" : "PM";
  $("clock").innerHTML =
    `${h12}:${pad(now.getMinutes())}:${pad(now.getSeconds())}<span class="ampm">${ampm}</span>`;
  $("sys-date").textContent =
    `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}`;
  const up = Math.floor((Date.now() - state.bootedAt) / 1000);
  $("sys-uptime").textContent =
    `${pad(Math.floor(up / 3600))}:${pad(Math.floor((up % 3600) / 60))}:${pad(up % 60)}`;
}

/* ───────── hardware stats ───────── */

function setMeter(bar, val, pct, text) {
  $(bar).style.width = (pct == null ? 0 : Math.min(100, pct)) + "%";
  $(bar).classList.toggle("hot", pct != null && pct >= 85);
  $(val).textContent = text;
}

function fmtGB(bytes) {
  if (bytes == null) return "?";
  const gb = bytes / 1024 ** 3;
  return gb >= 1000 ? (gb / 1024).toFixed(2) + " TB" : gb.toFixed(gb >= 100 ? 0 : 1) + " GB";
}

async function refreshSystem() {
  try {
    const s = await (await fetch("/api/system")).json();

    const cpuPct = s.cpu.percent;
    setMeter("m-cpu", "v-cpu", cpuPct, cpuPct == null ? "—" : cpuPct.toFixed(0) + "%");
    $("mt-cpu").title = `${s.cpu.name} · ${s.cpu.cores} cores`;

    if (s.mem.total) {
      const pct = (s.mem.used / s.mem.total) * 100;
      setMeter("m-ram", "v-ram", pct, pct.toFixed(0) + "%");
      $("mt-ram").title = `${fmtGB(s.mem.used)} / ${fmtGB(s.mem.total)}`;
    } else {
      setMeter("m-ram", "v-ram", null, "—");
    }

    if (s.gpu) {
      setMeter("m-gpu", "v-gpu", s.gpu.util, s.gpu.util.toFixed(0) + "%");
      $("mt-gpu").title = s.gpu.vram_total
        ? `${s.gpu.name} · VRAM ${fmtGB(s.gpu.vram_used)} / ${fmtGB(s.gpu.vram_total)}`
        : s.gpu.name;
    } else {
      setMeter("m-gpu", "v-gpu", null, "N/A");
      $("mt-gpu").title = "no GPU detected (nvidia-smi / amdgpu sysfs)";
    }

    const dpct = (s.disk.used / s.disk.total) * 100;
    setMeter("m-drive", "v-drive", dpct, dpct.toFixed(0) + "%");
    $("mt-drive").title = `${fmtGB(s.disk.used)} used / ${fmtGB(s.disk.total)}`;

    const gpuName = s.gpu ? s.gpu.name : "no gpu";
    $("hw-detail").textContent =
      `${s.cpu.name.split("@")[0].trim()} · ${s.cpu.cores}c · ` +
      `${fmtGB(s.mem.total)} ram · ${gpuName} · ` +
      `drive ${fmtGB(s.disk.free)} free`;
  } catch (_) { /* server briefly unreachable */ }
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

/* ───────── reasoning (<think>) blocks ───────── */

function splitThink(text) {
  const parts = [];
  const re = /<think>([\s\S]*?)(<\/think>|$)/g;
  let last = 0, m;
  while ((m = re.exec(text))) {
    if (m.index > last) parts.push({ think: false, content: text.slice(last, m.index) });
    parts.push({ think: true, content: m[1], live: m[2] === "" });
    last = re.lastIndex;
  }
  if (last < text.length) parts.push({ think: false, content: text.slice(last) });
  return parts;
}

/* Render assistant text: markdown + collapsible REASONING cards. */
function renderAssistant(text) {
  const frag = document.createDocumentFragment();
  for (const part of splitThink(text ?? "")) {
    if (part.think) {
      if (!part.content.trim() && !part.live) continue;
      const card = document.createElement("details");
      card.className = "think-card";
      if (part.live) card.open = true;
      const summary = document.createElement("summary");
      summary.textContent = part.live ? "REASONING ▓" : "REASONING";
      const body = document.createElement("div");
      body.className = "think-body";
      body.append(renderMarkdown(part.content));
      card.append(summary, body);
      frag.append(card);
    } else if (part.content.trim()) {
      frag.append(renderMarkdown(part.content));
    }
  }
  return frag;
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
    const books = s.kiwix_books || [];
    $("kx-state").textContent = s.kiwix_online ? "ONLINE" : "OFFLINE";
    $("kx-state").style.color = s.kiwix_online ? "var(--accent)" : "";
    $("kx-books").textContent = books.length;
    $("kx-books").title = books.join("\n");
    $("boot-knowledge").textContent = s.kiwix_online
      ? `> knowledge base mounted: ${books.length} book(s) — wikipedia & docs on-drive`
      : "> knowledge base not running — run scripts/pull-knowledge to add wikipedia & docs";
    state.kiwixViewer = s.kiwix_url;
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
  switchView("chat");
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
      currentShell.querySelector(".content").append(renderAssistant(m.content));
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
    liveBlock.append(renderAssistant(streamedText));
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
  const mode = els.agentMode.checked ? "agent"
    : els.researchMode.checked ? "research" : "chat";
  logActivity(`query sent (${mode})`);
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
        research_mode: els.researchMode.checked,
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

/* ───────── GET MORE (store + updates) ───────── */

const store = { open: false, timer: null };

function switchView(view) {
  store.open = view === "store";
  $("chat").hidden = store.open;
  $("composer").hidden = store.open;
  $("store").hidden = !store.open;
  $("tab-chat").classList.toggle("active", !store.open);
  $("tab-store").classList.toggle("active", store.open);
  if (store.open) {
    refreshStore();
    if (!store.timer) store.timer = setInterval(refreshStore, 2000);
  } else if (store.timer) {
    clearInterval(store.timer);
    store.timer = null;
  }
}

function fmtBytes(n) {
  if (!n) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let i = 0;
  while (n >= 1024 && i < units.length - 1) { n /= 1024; i++; }
  return `${n.toFixed(n >= 100 ? 0 : 1)} ${units[i]}`;
}

function storeRow(kind, item, job) {
  const row = document.createElement("div");
  row.className = "store-row";

  const name = document.createElement("span");
  name.className = "item-name";
  name.textContent = kind === "model" ? item.id : item.title;
  row.append(name);

  if (item.cat) {
    const cat = document.createElement("span");
    cat.className = "item-cat";
    cat.textContent = item.cat.toUpperCase();
    row.append(cat);
  }

  const desc = document.createElement("span");
  desc.className = "item-desc";
  desc.textContent = item.desc || "";
  row.append(desc);

  const size = document.createElement("span");
  size.className = "item-size";
  size.textContent = item.size;
  row.append(size);

  const state = document.createElement("span");
  state.className = "item-state";

  if (job && job.status === "running") {
    const wrap = document.createElement("span");
    wrap.className = "item-progress";
    const bar = document.createElement("span");
    bar.className = "pbar";
    const fill = document.createElement("span");
    fill.className = "pbar-fill";
    const pct = job.total ? Math.min(100, (job.done / job.total) * 100) : 0;
    fill.style.width = pct + "%";
    bar.append(fill);
    const label = document.createElement("span");
    label.className = "pbar-label";
    label.textContent = job.total
      ? `${fmtBytes(job.done)} / ${fmtBytes(job.total)} — ${job.detail}`
      : job.detail;
    wrap.append(bar, label);
    const cancel = document.createElement("button");
    cancel.className = "btn-get btn-cancel";
    cancel.textContent = "✕";
    cancel.title = "Cancel";
    cancel.addEventListener("click", () => cancelDownload(kind, item.id));
    state.append(wrap, cancel);
  } else if (item.installed || (job && job.status === "done")) {
    const lbl = document.createElement("span");
    lbl.className = "item-installed";
    lbl.textContent = "INSTALLED";
    state.append(lbl);
  } else {
    if (job && (job.status === "error" || job.status === "cancelled")) {
      const label = document.createElement("span");
      label.className = "pbar-label err";
      label.textContent = job.detail;
      label.title = job.detail;
      state.append(label);
    }
    const btn = document.createElement("button");
    btn.className = "btn-get";
    btn.textContent = "GET";
    btn.addEventListener("click", () => startDownload(kind, item.id));
    state.append(btn);
  }
  row.append(state);
  return row;
}

async function refreshStore() {
  try {
    const res = await fetch("/api/downloads");
    const data = await res.json();
    const anyRunning = Object.values(data.jobs || {})
      .some((j) => j.status === "running");
    const modelBox = $("store-models");
    modelBox.innerHTML = "";
    for (const m of data.models) {
      modelBox.append(storeRow("model", m, data.jobs[`model:${m.id}`]));
    }
    const zimBox = $("store-zims");
    zimBox.innerHTML = "";
    for (const z of data.zims) {
      zimBox.append(storeRow("zim", z, data.jobs[`zim:${z.id}`]));
    }
    // keep polling in the background while something is downloading
    if (anyRunning && !store.timer) store.timer = setInterval(refreshStore, 2000);
    if (!anyRunning && !store.open && store.timer) {
      clearInterval(store.timer);
      store.timer = null;
    }
  } catch (_) { /* server briefly unreachable */ }
}

async function startDownload(kind, id) {
  const res = await fetch("/api/downloads/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ kind, id }),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) logActivity(`download refused: ${data.error || res.status}`, true);
  else logActivity(`download started: ${id}`);
  refreshStore();
}

async function cancelDownload(kind, id) {
  await fetch("/api/downloads/cancel", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ job: `${kind}:${id}` }),
  });
  logActivity(`download cancelled: ${id}`, true);
}

async function checkUpdates() {
  $("upd-status").className = "upd-status";
  $("upd-status").textContent = "contacting github…";
  $("btn-apply-upd").hidden = true;
  try {
    const res = await fetch("/api/updates/check");
    const u = await res.json();
    $("upd-current").textContent = `local: ${u.current || "unknown"}`;
    if (!u.online) {
      $("upd-status").textContent = `offline — ${u.error || "no connection to GitHub"}`;
      logActivity("update check failed: offline", true);
      return;
    }
    if (u.update_available) {
      $("upd-status").className = "upd-status good";
      $("upd-status").textContent =
        `update available → ${u.latest} (${u.latest_date})\n"${u.latest_message}"`;
      $("btn-apply-upd").hidden = false;
      logActivity(`update available: ${u.latest}`);
    } else {
      $("upd-status").textContent = `up to date with main (${u.latest})`;
      logActivity("xdrive is up to date", true);
    }
  } catch (_) {
    $("upd-status").textContent = "update check failed";
  }
}

async function applyUpdate() {
  $("upd-status").textContent = "pulling from github…";
  const res = await fetch("/api/updates/apply", { method: "POST" });
  const r = await res.json();
  $("upd-status").className = "upd-status" + (r.ok ? " good" : "");
  $("upd-status").textContent = r.ok
    ? `${r.output}\n\n${r.note}`
    : `update failed:\n${r.output}`;
  $("btn-apply-upd").hidden = true;
  logActivity(r.ok ? "update applied — restart xdrive" : "update failed", !r.ok);
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
els.researchMode.addEventListener("change", () => {
  logActivity(`research mode ${els.researchMode.checked ? "ENABLED" : "disabled"}`);
});

/* ───────── knowledge search ───────── */

$("kx-query").addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  const q = $("kx-query").value.trim();
  if (!q) return;
  const box = $("kx-results");
  box.innerHTML = "<div class='kx-hit dim'>searching…</div>";
  try {
    const res = await fetch(`/api/knowledge/search?q=${encodeURIComponent(q)}`);
    const data = await res.json();
    box.innerHTML = "";
    if (!res.ok || !(data.results || []).length) {
      box.innerHTML = "<div class='kx-hit dim'>no results</div>";
      return;
    }
    for (const r of data.results.slice(0, 6)) {
      const a = document.createElement("a");
      a.className = "kx-hit";
      a.textContent = r.title || r.path;
      a.title = r.snippet || r.path;
      a.href = `${data.viewer}/viewer#${r.path}`;
      a.target = "_blank";
      a.rel = "noopener";
      box.append(a);
    }
    logActivity(`knowledge search: ${q}`, true);
  } catch (_) {
    box.innerHTML = "<div class='kx-hit dim'>knowledge base offline</div>";
  }
});

$("tab-chat").addEventListener("click", () => switchView("chat"));
$("tab-store").addEventListener("click", () => switchView("store"));
$("btn-check-upd").addEventListener("click", checkUpdates);
$("btn-apply-upd").addEventListener("click", applyUpdate);

$("btn-new").addEventListener("click", () => { switchView("chat"); newChat(); });
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
refreshSystem();
setTimeout(refreshSystem, 1200); // second sample so CPU% has a delta
refreshConversations();
setInterval(refreshStatus, 20000);
setInterval(refreshSystem, 5000);
logActivity("xDrive terminal ready");
els.input.focus();
