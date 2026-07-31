#!/usr/bin/env python3
"""Ember — a fully offline AI assistant.

A single-file, zero-dependency (Python stdlib only) local server that:
  * serves the Ember web UI
  * talks to a local LLM runtime (Ollama or llama.cpp server) over the
    OpenAI-compatible chat completions API
  * streams responses to the browser via Server-Sent Events
  * persists conversations as JSON files on disk
  * provides an "agent mode" tool loop (read/write files, list dirs, run
    commands inside a sandboxed workspace directory) so the model can do
    real coding tasks

Runs on Linux and Windows. No pip installs, no internet required.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_NAME = "Ember"
ROOT = Path(__file__).resolve().parent.parent
WEB_DIR = ROOT / "web"
CONFIG_PATH = ROOT / "config.json"

DEFAULT_CONFIG = {
    # Where Ember keeps conversations and the agent workspace. Relative
    # paths are resolved against the repo root, so everything stays on the
    # same drive as the app by default.
    "data_dir": "data",
    # Local LLM runtime. "auto" probes Ollama (11434) then llama.cpp (8080).
    "backend_url": "auto",
    "default_model": "",
    "temperature": 0.7,
    "system_prompt": (
        "You are Ember, a helpful offline AI assistant. You are skilled at "
        "programming, debugging, and explaining technical topics, and equally "
        "comfortable with general questions. Answer directly and format code "
        "in fenced blocks with a language tag."
    ),
    # Hard cap on agent-mode tool iterations per user message.
    "max_tool_steps": 8,
    # Seconds before a run_command tool call is killed.
    "command_timeout": 120,
    "host": "127.0.0.1",
    "port": 8484,
}

KNOWN_BACKENDS = [
    "http://127.0.0.1:11434",  # Ollama
    "http://127.0.0.1:8080",   # llama.cpp llama-server
]

AGENT_PROMPT = """
You can use tools to work on files and run commands inside a workspace
directory. To call a tool, output a fenced block exactly like this and then
stop your reply:

```tool
{"tool": "run_command", "args": {"command": "ls -la"}}
```

Available tools:
- list_dir   {"path": "."}                    — list a directory
- read_file  {"path": "src/main.py"}          — read a text file
- write_file {"path": "src/main.py", "content": "..."} — create/overwrite a file
- run_command {"command": "python main.py"}   — run a shell command (cwd = workspace)

Rules: paths are relative to the workspace; one tool call per reply; after a
tool result arrives, continue the task or give your final answer. When the
task is done, reply normally without any tool block.
""".strip()

TOOL_BLOCK_RE = re.compile(r"```tool\s*\n(.*?)```", re.DOTALL)


# --------------------------------------------------------------------------
# Config & storage helpers
# --------------------------------------------------------------------------

_config_lock = threading.Lock()


def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if CONFIG_PATH.exists():
        try:
            cfg.update(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError) as exc:
            print(f"[{APP_NAME}] warning: could not read config.json: {exc}")
    return cfg


def save_config(cfg):
    with _config_lock:
        CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def data_dir(cfg):
    p = Path(cfg["data_dir"])
    if not p.is_absolute():
        p = ROOT / p
    return p


def conversations_dir(cfg):
    p = data_dir(cfg) / "conversations"
    p.mkdir(parents=True, exist_ok=True)
    return p


def workspace_dir(cfg):
    p = data_dir(cfg) / "workspace"
    p.mkdir(parents=True, exist_ok=True)
    return p


def load_conversation(cfg, conv_id):
    path = conversations_dir(cfg) / f"{conv_id}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def save_conversation(cfg, conv):
    conv["updated"] = time.time()
    path = conversations_dir(cfg) / f"{conv['id']}.json"
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(conv, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def list_conversations(cfg):
    items = []
    for path in conversations_dir(cfg).glob("*.json"):
        try:
            conv = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "id": conv["id"],
                "title": conv.get("title", "Untitled"),
                "updated": conv.get("updated", 0),
                "message_count": len(conv.get("messages", [])),
            })
        except (json.JSONDecodeError, OSError, KeyError):
            continue
    items.sort(key=lambda c: c["updated"], reverse=True)
    return items


# --------------------------------------------------------------------------
# LLM backend (Ollama / llama.cpp — both speak the OpenAI chat API)
# --------------------------------------------------------------------------

def probe_backend(url):
    """Return (kind, models) if an LLM runtime answers at `url`, else None."""
    # Ollama native endpoint gives us model names with sizes.
    try:
        with urllib.request.urlopen(f"{url}/api/tags", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m["name"] for m in data.get("models", [])]
            return ("ollama", models)
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        pass
    try:
        with urllib.request.urlopen(f"{url}/v1/models", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            models = [m.get("id", "default") for m in data.get("data", [])]
            return ("openai", models)
    except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
        pass
    return None


def resolve_backend(cfg):
    """Return (url, kind, models) for the active backend, or (None, None, [])."""
    configured = cfg.get("backend_url", "auto")
    candidates = KNOWN_BACKENDS if configured in ("", "auto") else [configured.rstrip("/")]
    for url in candidates:
        found = probe_backend(url)
        if found:
            return url, found[0], found[1]
    return None, None, []


def stream_chat(backend_url, model, messages, temperature):
    """Yield content tokens from the backend's OpenAI-compatible stream."""
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "stream": True,
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{backend_url}/v1/chat/completions",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            line = raw.decode("utf-8", errors="replace").strip()
            if not line.startswith("data:"):
                continue
            chunk = line[5:].strip()
            if chunk == "[DONE]":
                break
            try:
                delta = json.loads(chunk)["choices"][0]["delta"]
            except (json.JSONDecodeError, KeyError, IndexError):
                continue
            token = delta.get("content")
            if token:
                yield token


# --------------------------------------------------------------------------
# Agent tools (sandboxed to the workspace directory)
# --------------------------------------------------------------------------

def safe_path(workspace, rel):
    """Resolve `rel` inside the workspace; refuse anything that escapes it."""
    candidate = (workspace / rel).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"path escapes the workspace: {rel}")
    return candidate


def run_tool(cfg, name, args):
    ws = workspace_dir(cfg).resolve()
    if name == "list_dir":
        target = safe_path(ws, args.get("path", "."))
        if not target.is_dir():
            return f"error: not a directory: {args.get('path', '.')}"
        entries = []
        for entry in sorted(target.iterdir()):
            kind = "dir " if entry.is_dir() else "file"
            size = entry.stat().st_size if entry.is_file() else ""
            entries.append(f"{kind}  {entry.name}  {size}")
        return "\n".join(entries) if entries else "(empty directory)"
    if name == "read_file":
        target = safe_path(ws, args["path"])
        if not target.is_file():
            return f"error: no such file: {args['path']}"
        text = target.read_text(encoding="utf-8", errors="replace")
        limit = 60_000
        if len(text) > limit:
            text = text[:limit] + f"\n... (truncated, {len(text)} chars total)"
        return text
    if name == "write_file":
        target = safe_path(ws, args["path"])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(args.get("content", ""), encoding="utf-8")
        return f"wrote {len(args.get('content', ''))} chars to {args['path']}"
    if name == "run_command":
        cmd = args["command"]
        try:
            proc = subprocess.run(
                cmd,
                shell=True,
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=cfg.get("command_timeout", 120),
            )
            out = (proc.stdout or "") + (proc.stderr or "")
            out = out.strip() or "(no output)"
            if len(out) > 60_000:
                out = out[:60_000] + "\n... (truncated)"
            return f"exit code {proc.returncode}\n{out}"
        except subprocess.TimeoutExpired:
            return "error: command timed out"
    return f"error: unknown tool: {name}"


def extract_tool_call(text):
    """Return (name, args) for the first tool block in `text`, else None."""
    match = TOOL_BLOCK_RE.search(text)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(1))
        return parsed["tool"], parsed.get("args", {})
    except (json.JSONDecodeError, KeyError, TypeError):
        return None


# --------------------------------------------------------------------------
# HTTP handler
# --------------------------------------------------------------------------

MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
    ".woff2": "font/woff2",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt, *args):  # quieter default logging
        if "/api/" in (args[0] if args else ""):
            return
        sys.stderr.write(f"[{APP_NAME}] {fmt % args}\n")

    # ---- plumbing -------------------------------------------------------

    def send_json(self, obj, status=200):
        body = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return {}
        return json.loads(self.rfile.read(length).decode("utf-8"))

    def send_sse_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

    def sse(self, obj):
        self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ---- routing --------------------------------------------------------

    def do_GET(self):
        path = self.path.split("?", 1)[0]
        if path == "/api/status":
            return self.handle_status()
        if path == "/api/config":
            return self.handle_get_config()
        if path == "/api/conversations":
            return self.send_json(list_conversations(load_config()))
        if path.startswith("/api/conversations/"):
            conv = load_conversation(load_config(), path.rsplit("/", 1)[1])
            if conv is None:
                return self.send_json({"error": "not found"}, 404)
            return self.send_json(conv)
        return self.serve_static(path)

    def do_POST(self):
        path = self.path.split("?", 1)[0]
        try:
            if path == "/api/chat":
                return self.handle_chat()
            if path == "/api/config":
                return self.handle_put_config()
            if path == "/api/stop":
                return self.send_json({"ok": True})
        except (json.JSONDecodeError, KeyError, ValueError) as exc:
            return self.send_json({"error": str(exc)}, 400)
        return self.send_json({"error": "not found"}, 404)

    def do_DELETE(self):
        path = self.path.split("?", 1)[0]
        if path.startswith("/api/conversations/"):
            cfg = load_config()
            target = conversations_dir(cfg) / f"{path.rsplit('/', 1)[1]}.json"
            if target.exists() and target.parent == conversations_dir(cfg):
                target.unlink()
            return self.send_json({"ok": True})
        return self.send_json({"error": "not found"}, 404)

    # ---- static files ---------------------------------------------------

    def serve_static(self, path):
        if path in ("/", ""):
            path = "/index.html"
        target = (WEB_DIR / path.lstrip("/")).resolve()
        if WEB_DIR.resolve() not in target.parents or not target.is_file():
            return self.send_json({"error": "not found"}, 404)
        body = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(target.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- API handlers ---------------------------------------------------

    def handle_status(self):
        cfg = load_config()
        url, kind, models = resolve_backend(cfg)
        self.send_json({
            "app": APP_NAME,
            "backend_url": url,
            "backend_kind": kind,
            "online": url is not None,
            "models": models,
            "default_model": cfg.get("default_model") or (models[0] if models else ""),
            "workspace": str(workspace_dir(cfg)),
        })

    def handle_get_config(self):
        cfg = load_config()
        self.send_json(cfg)

    def handle_put_config(self):
        incoming = self.read_json()
        cfg = load_config()
        for key in ("backend_url", "default_model", "temperature",
                    "system_prompt", "data_dir", "max_tool_steps",
                    "command_timeout"):
            if key in incoming:
                cfg[key] = incoming[key]
        save_config(cfg)
        self.send_json(cfg)

    def handle_chat(self):
        body = self.read_json()
        cfg = load_config()
        user_text = (body.get("message") or "").strip()
        if not user_text:
            return self.send_json({"error": "empty message"}, 400)

        backend_url, _, models = resolve_backend(cfg)
        if backend_url is None:
            return self.send_json({
                "error": "No local LLM runtime found. Start Ollama or "
                         "llama-server, then try again."
            }, 503)

        model = body.get("model") or cfg.get("default_model") or (models[0] if models else "")
        if not model:
            return self.send_json({"error": "No models installed in the runtime."}, 503)

        agent_mode = bool(body.get("agent_mode"))
        temperature = float(body.get("temperature", cfg.get("temperature", 0.7)))

        conv_id = body.get("conversation_id")
        conv = load_conversation(cfg, conv_id) if conv_id else None
        if conv is None:
            conv = {
                "id": uuid.uuid4().hex[:12],
                "title": user_text[:60] + ("…" if len(user_text) > 60 else ""),
                "created": time.time(),
                "messages": [],
            }
        conv["messages"].append({"role": "user", "content": user_text})
        save_conversation(cfg, conv)

        system_prompt = cfg.get("system_prompt", "")
        if agent_mode:
            system_prompt = f"{system_prompt}\n\n{AGENT_PROMPT}"

        self.send_sse_headers()
        self.sse({"type": "meta", "conversation_id": conv["id"], "model": model})

        try:
            self.run_chat_loop(cfg, backend_url, model, temperature,
                               system_prompt, conv, agent_mode)
        except (BrokenPipeError, ConnectionResetError):
            save_conversation(cfg, conv)
            return
        except urllib.error.URLError as exc:
            self.sse({"type": "error", "message": f"backend error: {exc}"})
        except OSError as exc:
            self.sse({"type": "error", "message": str(exc)})
        self.sse({"type": "done"})

    def run_chat_loop(self, cfg, backend_url, model, temperature,
                      system_prompt, conv, agent_mode):
        """Stream a reply; in agent mode, execute tool calls and continue."""
        max_steps = int(cfg.get("max_tool_steps", 8)) if agent_mode else 1

        for _ in range(max_steps):
            llm_messages = [{"role": "system", "content": system_prompt}]
            for msg in conv["messages"]:
                if msg["role"] == "tool":
                    llm_messages.append({
                        "role": "user",
                        "content": f"[tool result]\n{msg['content']}",
                    })
                else:
                    llm_messages.append({"role": msg["role"], "content": msg["content"]})

            assistant_text = ""
            for token in stream_chat(backend_url, model, llm_messages, temperature):
                assistant_text += token
                self.sse({"type": "token", "text": token})

            conv["messages"].append({"role": "assistant", "content": assistant_text})
            save_conversation(cfg, conv)

            call = extract_tool_call(assistant_text) if agent_mode else None
            if call is None:
                return

            name, args = call
            self.sse({"type": "tool_call", "name": name, "args": args})
            try:
                result = run_tool(cfg, name, args)
            except (ValueError, KeyError, OSError) as exc:
                result = f"error: {exc}"
            self.sse({"type": "tool_result", "name": name, "output": result})
            conv["messages"].append({
                "role": "tool",
                "content": f"{name} -> {result}",
                "tool": name,
            })
            save_conversation(cfg, conv)

        self.sse({"type": "error",
                  "message": "Stopped: reached the tool-step limit for one message."})


def main():
    cfg = load_config()
    if not CONFIG_PATH.exists():
        save_config(cfg)
    conversations_dir(cfg)
    workspace_dir(cfg)

    host = cfg.get("host", "127.0.0.1")
    port = int(os.environ.get("EMBER_PORT", cfg.get("port", 8484)))
    server = ThreadingHTTPServer((host, port), Handler)

    url, kind, models = resolve_backend(cfg)
    print(f"  ┌─────────────────────────────────────────────┐")
    print(f"  │  {APP_NAME} — offline AI assistant              │")
    print(f"  └─────────────────────────────────────────────┘")
    print(f"  UI:        http://{host}:{port}")
    if url:
        print(f"  LLM:       {kind} at {url} ({len(models)} model(s))")
    else:
        print(f"  LLM:       none detected — start Ollama or llama-server")
    print(f"  Data:      {data_dir(cfg)}")
    print(f"  Workspace: {workspace_dir(cfg)}")
    print(f"  Press Ctrl+C to quit.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{APP_NAME}] bye")


if __name__ == "__main__":
    main()
