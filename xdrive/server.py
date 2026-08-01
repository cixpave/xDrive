#!/usr/bin/env python3
"""xDrive — a fully offline AI assistant.

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

import html as html_mod
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

APP_NAME = "xDrive"
SERVER_STARTED = time.time()
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
        "You are xDrive, a helpful offline AI assistant. You are skilled at "
        "programming, debugging, and explaining technical topics, and equally "
        "comfortable with general questions. Answer directly and format code "
        "in fenced blocks with a language tag."
    ),
    # Hard cap on agent-mode tool iterations per user message.
    "max_tool_steps": 8,
    # Seconds before a run_command tool call is killed.
    "command_timeout": 120,
    # Offline knowledge base (kiwix-serve with ZIM files: Wikipedia, dev
    # docs, ...). "auto" probes the default local port.
    "kiwix_url": "auto",
    "host": "127.0.0.1",
    "port": 8484,
}

KNOWN_BACKENDS = [
    "http://127.0.0.1:11434",  # Ollama
    "http://127.0.0.1:8080",   # llama.cpp llama-server
]

KNOWN_KIWIX = [
    "http://127.0.0.1:8181",   # kiwix-serve (started by start.sh / start.bat)
]

THINK_RE = re.compile(r"<think>.*?(?:</think>|$)", re.DOTALL)

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

KNOWLEDGE_PROMPT = """
A local offline knowledge base is available (Wikipedia, programming language
documentation, and more). To consult it, output a fenced block exactly like
this and then stop your reply:

```tool
{"tool": "search_knowledge", "args": {"query": "quicksort algorithm"}}
```

Knowledge tools:
- search_knowledge {"query": "..."}          — full-text search across all books
- read_knowledge  {"path": "book/A/Article"} — read one article as plain text

Rules: one tool call per reply; after results arrive, either read a
promising article or answer. Mention which articles you used in your final
answer. Use the knowledge base for factual, historical, scientific, or API/
syntax questions; skip it when you already know the answer with confidence.
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


# Probe results are cached briefly: the UI polls status/downloads every few
# seconds, and probing a *down* runtime costs two 2-second timeouts — without
# a cache every request in between stalls behind that.
_probe_lock = threading.Lock()
_probe_cache = {}


def _cached_probe(key, ttl, fn):
    now = time.time()
    with _probe_lock:
        hit = _probe_cache.get(key)
        if hit and hit[0] > now:
            return hit[1]
    value = fn()
    with _probe_lock:
        _probe_cache[key] = (now + ttl, value)
    return value


def clear_probe_cache():
    with _probe_lock:
        _probe_cache.clear()


def resolve_backend(cfg):
    """Return (url, kind, models) for the active backend, or (None, None, [])."""
    configured = cfg.get("backend_url", "auto")

    def _probe():
        candidates = (KNOWN_BACKENDS if configured in ("", "auto")
                      else [configured.rstrip("/")])
        for url in candidates:
            found = probe_backend(url)
            if found:
                return url, found[0], found[1]
        return None, None, []

    return _cached_probe(("backend", configured), 3.0, _probe)


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
# Offline knowledge base (kiwix-serve: Wikipedia, dev docs, ... as ZIM files)
# --------------------------------------------------------------------------

def _local_name(tag):
    return tag.rsplit("}", 1)[-1]


def kiwix_books(url):
    """Return [{name, title}] served by kiwix-serve at `url`, or None."""
    try:
        with urllib.request.urlopen(f"{url}/catalog/v2/entries?count=200", timeout=2) as resp:
            root = ET.fromstring(resp.read())
    except (urllib.error.URLError, ET.ParseError, OSError, TimeoutError):
        return None
    books = []
    for entry in root.iter():
        if _local_name(entry.tag) != "entry":
            continue
        name = title = None
        for child in entry:
            if _local_name(child.tag) == "name":
                name = (child.text or "").strip()
            elif _local_name(child.tag) == "title":
                title = (child.text or "").strip()
        if name:
            books.append({"name": name, "title": title or name})
    return books


def resolve_kiwix(cfg):
    """Return (url, books) for the knowledge base, or (None, [])."""
    configured = cfg.get("kiwix_url", "auto")

    def _probe():
        candidates = (KNOWN_KIWIX if configured in ("", "auto")
                      else [configured.rstrip("/")])
        for url in candidates:
            books = kiwix_books(url)
            if books is not None:
                return url, books
        return None, []

    return _cached_probe(("kiwix", configured), 3.0, _probe)


class _SearchResultParser(HTMLParser):
    """Pull (href, title, snippet) triples out of a kiwix-serve results page."""

    def __init__(self):
        super().__init__()
        self.results = []
        self._in_link = False
        self._in_cite = False
        self._current = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and attrs.get("href") and "pattern=" not in attrs["href"]:
            href = attrs["href"]
            if "/viewer#" in href or "/content/" in href:
                self._current = {"href": href, "title": "", "snippet": ""}
                self._in_link = True
        elif tag == "cite" and self._current:
            self._in_cite = True

    def handle_endtag(self, tag):
        if tag == "a" and self._in_link:
            self._in_link = False
        elif tag == "cite" and self._in_cite:
            self._in_cite = False
            if self._current:
                self.results.append(self._current)
                self._current = None

    def handle_data(self, data):
        if self._in_link and self._current is not None:
            self._current["title"] += data
        elif self._in_cite and self._current is not None:
            self._current["snippet"] += data


def _normalize_kiwix_path(href):
    """Turn any kiwix result href into a 'book/namespace/Article' path."""
    href = html_mod.unescape(href)
    if "/viewer#" in href:
        return href.split("/viewer#", 1)[1]
    if "/content/" in href:
        return href.split("/content/", 1)[1]
    return href.lstrip("/")


def kiwix_search(url, books, query, limit=8):
    """Full-text search; falls back to title suggestions if parsing fails."""
    params = [("pattern", query), ("pageLength", str(limit))]
    for book in books[:10]:
        params.append(("books.name", book["name"]))
    qs = urllib.parse.urlencode(params)
    results = []
    try:
        with urllib.request.urlopen(f"{url}/search?{qs}", timeout=8) as resp:
            parser = _SearchResultParser()
            parser.feed(resp.read().decode("utf-8", errors="replace"))
        for r in parser.results[:limit]:
            results.append({
                "title": " ".join(r["title"].split()),
                "path": _normalize_kiwix_path(r["href"]),
                "snippet": " ".join(r["snippet"].split())[:240],
            })
    except (urllib.error.URLError, OSError, TimeoutError):
        pass
    if results:
        return results
    # Fallback: per-book title suggestions (prefix match, no snippets).
    for book in books[:10]:
        qs = urllib.parse.urlencode({"content": book["name"], "term": query})
        try:
            with urllib.request.urlopen(f"{url}/suggest?{qs}", timeout=4) as resp:
                for s in json.loads(resp.read().decode("utf-8")):
                    if s.get("kind") == "path" and s.get("path"):
                        results.append({
                            "title": " ".join(s.get("value", "").split()),
                            "path": f"{book['name']}/{s['path'].lstrip('/')}",
                            "snippet": "",
                        })
        except (urllib.error.URLError, json.JSONDecodeError, OSError, TimeoutError):
            continue
    return results[:limit]


class _TextExtractor(HTMLParser):
    SKIP = {"script", "style", "nav", "header", "footer"}

    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip_depth = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self._skip_depth += 1

    def handle_endtag(self, tag):
        if tag in self.SKIP and self._skip_depth:
            self._skip_depth -= 1
        elif tag in ("p", "div", "li", "tr", "h1", "h2", "h3", "h4", "br"):
            self.parts.append("\n")

    def handle_data(self, data):
        if not self._skip_depth:
            self.parts.append(data)


def kiwix_read(url, path, limit=20_000):
    """Fetch one article and reduce it to plain text for the model."""
    path = _normalize_kiwix_path(path)
    quoted = urllib.parse.quote(path, safe="/#?&=%")
    with urllib.request.urlopen(f"{url}/content/{quoted}", timeout=10) as resp:
        page = resp.read().decode("utf-8", errors="replace")
    extractor = _TextExtractor()
    extractor.feed(page)
    text = "".join(extractor.parts)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    if len(text) > limit:
        text = text[:limit] + f"\n... (truncated, {len(text)} chars total)"
    return text or "(article is empty or could not be extracted)"


# --------------------------------------------------------------------------
# Downloads (models + knowledge ZIMs) and app updates from GitHub
# --------------------------------------------------------------------------

GITHUB_REPO = "cixpave/xDrive"
GH_API = os.environ.get("XDRIVE_GH_API", "https://api.github.com")
ZIM_BASE = os.environ.get("XDRIVE_ZIM_BASE", "https://download.kiwix.org/zim/")

MODEL_CATALOG = [
    {"id": "qwen2.5:3b",           "size": "1.9 GB", "cat": "general",   "desc": "instant answers on any hardware"},
    {"id": "llama3.2:3b",          "size": "2.0 GB", "cat": "general",   "desc": "meta's small fast generalist"},
    {"id": "mistral:7b",           "size": "4.1 GB", "cat": "general",   "desc": "classic all-rounder"},
    {"id": "gemma2:9b",            "size": "5.4 GB", "cat": "general",   "desc": "google's mid-size generalist"},
    {"id": "qwen2.5:14b",          "size": "9.0 GB", "cat": "general",   "desc": "everyday chat, writing, Q&A"},
    {"id": "qwen2.5:32b",          "size": "20 GB",  "cat": "general",   "desc": "strong generalist (24 GB+ RAM)"},
    {"id": "llama3.3:70b",         "size": "43 GB",  "cat": "general",   "desc": "best general model (48 GB+ RAM)"},
    {"id": "qwen2.5-coder:7b",     "size": "4.7 GB", "cat": "coding",    "desc": "fast coding assistant"},
    {"id": "codellama:13b",        "size": "7.4 GB", "cat": "coding",    "desc": "meta's code specialist"},
    {"id": "deepseek-coder-v2:16b","size": "8.9 GB", "cat": "coding",    "desc": "MoE coder — fast for its strength"},
    {"id": "qwen2.5-coder:14b",    "size": "9.0 GB", "cat": "coding",    "desc": "daily-driver coding, 40+ languages"},
    {"id": "qwen2.5-coder:32b",    "size": "20 GB",  "cat": "coding",    "desc": "heavy coding (24 GB+ RAM)"},
    {"id": "deepseek-r1:8b",       "size": "5.2 GB", "cat": "reasoning", "desc": "compact step-by-step reasoning"},
    {"id": "phi4:14b",             "size": "9.1 GB", "cat": "reasoning", "desc": "microsoft's math/logic specialist"},
    {"id": "deepseek-r1:14b",      "size": "9.0 GB", "cat": "reasoning", "desc": "step-by-step reasoning"},
    {"id": "deepseek-r1:32b",      "size": "20 GB",  "cat": "reasoning", "desc": "heavy reasoning (24 GB+ RAM)"},
    {"id": "llava:7b",             "size": "4.7 GB", "cat": "vision",    "desc": "lightweight image understanding"},
    {"id": "llava:13b",            "size": "8.0 GB", "cat": "vision",    "desc": "describe screenshots and images"},
]

# every name verified against download.kiwix.org/zim/devdocs/
_DEVDOCS = ["python", "javascript", "typescript", "node", "html", "css", "c",
            "cpp", "rust", "go", "openjdk", "bash", "git", "docker",
            "postgresql", "react", "rails", "lua", "php", "ruby", "kotlin",
            "dart", "elixir", "haskell", "perl", "r", "scala", "nginx",
            "sqlite", "redis", "kubernetes", "cmake", "vue", "django",
            "flask", "numpy", "pandas", "godot", "love", "matplotlib"]

ZIM_CATALOG = [
    {"id": "wikipedia-full",   "title": "Wikipedia — full English, with images",
     "size": "~102 GB", "cat": "wiki", "files": ["wikipedia/wikipedia_en_all_maxi.zim"]},
    {"id": "wikipedia-nopic",  "title": "Wikipedia — full English, text only",
     "size": "~54 GB",  "cat": "wiki", "files": ["wikipedia/wikipedia_en_all_nopic.zim"]},
    {"id": "wikipedia-simple", "title": "Simple English Wikipedia",
     "size": "~2 GB",   "cat": "wiki", "files": ["wikipedia/wikipedia_en_simple_all_maxi.zim"]},
    {"id": "archwiki",         "title": "Arch Wiki",
     "size": "~30 MB",  "cat": "linux", "files": ["other/archlinux_en_all_maxi.zim"]},
    {"id": "devdocs-pack",     "title": f"DevDocs pack — {len(_DEVDOCS)} languages/tools incl. Lua",
     "size": "~2 GB",   "cat": "code", "files": [f"devdocs/devdocs_en_{d}.zim" for d in _DEVDOCS]},
    {"id": "stackoverflow",    "title": "Stack Overflow — every question & answer",
     "size": "~75 GB",  "cat": "code", "files": ["stack_exchange/stackoverflow.com_en_all.zim"]},
    {"id": "unix-se",          "title": "Unix & Linux StackExchange",
     "size": "~4 GB",   "cat": "linux", "files": ["stack_exchange/unix.stackexchange.com_en_all.zim"]},
    {"id": "askubuntu",        "title": "Ask Ubuntu — Q&A",
     "size": "~5 GB",   "cat": "linux", "files": ["stack_exchange/askubuntu.com_en_all.zim"]},
    {"id": "superuser",        "title": "Super User — power-user Q&A",
     "size": "~5 GB",   "cat": "misc", "files": ["stack_exchange/superuser.com_en_all.zim"]},
    {"id": "wiktionary",       "title": "Wiktionary — English dictionary",
     "size": "~7 GB",   "cat": "wiki", "files": ["wiktionary/wiktionary_en_all_nopic.zim"]},
    {"id": "wikibooks",        "title": "Wikibooks — textbooks & manuals",
     "size": "~4 GB",   "cat": "wiki", "files": ["wikibooks/wikibooks_en_all_maxi.zim"]},
    {"id": "wikiversity",      "title": "Wikiversity — courses & learning",
     "size": "~3 GB",   "cat": "wiki", "files": ["wikiversity/wikiversity_en_all_maxi.zim"]},
    {"id": "ifixit",           "title": "iFixit — repair guides for everything",
     "size": "~2 GB",   "cat": "misc", "files": ["ifixit/ifixit_en_all.zim"]},
    {"id": "gutenberg",        "title": "Project Gutenberg — 60k+ books",
     "size": "~65 GB",  "cat": "misc", "files": ["gutenberg/gutenberg_en_all.zim"]},
]

_jobs_lock = threading.Lock()
JOBS = {}  # job_id -> {status, detail, done, total, cancel}


def job_update(job_id, **fields):
    with _jobs_lock:
        if job_id in JOBS:
            JOBS[job_id].update(fields)


def job_cancelled(job_id):
    with _jobs_lock:
        return JOBS.get(job_id, {}).get("cancel", False)


def start_job(job_id, target, *args):
    """Spawn a background download thread unless one is already running."""
    with _jobs_lock:
        if JOBS.get(job_id, {}).get("status") == "running":
            return False
        JOBS[job_id] = {"status": "running", "detail": "starting…",
                        "done": 0, "total": 0, "cancel": False}
    threading.Thread(target=target, args=(job_id, *args), daemon=True).start()
    return True


def pull_model_job(job_id, backend_url, model):
    """Pull a model through Ollama's streaming /api/pull endpoint."""
    try:
        payload = json.dumps({"model": model, "name": model, "stream": True}).encode()
        req = urllib.request.Request(
            f"{backend_url}/api/pull", data=payload,
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            for raw in resp:
                if job_cancelled(job_id):
                    job_update(job_id, status="cancelled", detail="cancelled")
                    return
                try:
                    ev = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if ev.get("error"):
                    job_update(job_id, status="error", detail=ev["error"])
                    return
                fields = {"detail": ev.get("status", "")}
                if ev.get("total"):
                    fields["total"] = ev["total"]
                    fields["done"] = ev.get("completed", 0)
                job_update(job_id, **fields)
        job_update(job_id, status="done", detail="installed")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        job_update(job_id, status="error", detail=f"pull failed: {exc}")


def resolve_zim_file(rel):
    """Resolve 'devdocs/devdocs_en_python.zim' to the latest dated file.

    Kiwix only hosts dated snapshots (name_YYYY-MM.zim), so we read the
    directory listing and pick the newest match.
    """
    folder, fname = rel.rsplit("/", 1)
    stem = fname[:-4] if fname.endswith(".zim") else fname
    req = urllib.request.Request(f"{ZIM_BASE}{folder}/",
                                 headers={"User-Agent": "xDrive"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        listing = resp.read().decode("utf-8", errors="replace")
    dates = re.findall(
        rf'href="{re.escape(stem)}_(\d{{4}}-\d{{2}})\.zim"', listing)
    if not dates:
        raise FileNotFoundError(
            f"{stem} not found on the download server (catalog outdated?)")
    return f"{folder}/{stem}_{max(dates)}.zim"


def zim_stem_installed(lib, rel):
    """True if any snapshot of this ZIM (dated or not) is in library/."""
    stem = rel.rsplit("/", 1)[-1][:-4]
    return any(lib.glob(f"{stem}.zim")) or any(lib.glob(f"{stem}_*.zim"))


def download_zim_job(job_id, files):
    """Download ZIM file(s) to library/ with resume support."""
    lib = ROOT / "library"
    lib.mkdir(exist_ok=True)
    downloaded_any = False
    try:
        for idx, rel in enumerate(files, 1):
            if zim_stem_installed(lib, rel):
                continue
            job_update(job_id, detail=f"resolving latest version… ({idx}/{len(files)})")
            rel = resolve_zim_file(rel)
            name = rel.rsplit("/", 1)[-1]
            dest = lib / name
            if dest.exists():
                continue
            part = lib / (name + ".part")
            offset = part.stat().st_size if part.exists() else 0
            headers = {"User-Agent": "xDrive"}
            if offset:
                headers["Range"] = f"bytes={offset}-"
            req = urllib.request.Request(ZIM_BASE + rel, headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                resumed = resp.status == 206
                if not resumed:
                    offset = 0
                total = int(resp.headers.get("Content-Length") or 0) + offset
                job_update(job_id, detail=f"{name} ({idx}/{len(files)})",
                           total=total, done=offset)
                with open(part, "ab" if resumed else "wb") as f:
                    while True:
                        if job_cancelled(job_id):
                            job_update(job_id, status="cancelled",
                                       detail="cancelled — GET again to resume")
                            return
                        chunk = resp.read(512 * 1024)
                        if not chunk:
                            break
                        f.write(chunk)
                        offset += len(chunk)
                        job_update(job_id, done=offset)
            if total and offset < total:
                job_update(job_id, status="error",
                           detail="connection dropped — GET again to resume")
                return
            part.replace(dest)
            downloaded_any = True
        # only bounce kiwix-serve when something new actually arrived
        mounted = restart_kiwix() if downloaded_any else False
        job_update(job_id, status="done",
                   detail="installed — knowledge base mounted" if mounted
                   else "installed")
    except (urllib.error.URLError, OSError, TimeoutError) as exc:
        job_update(job_id, status="error", detail=f"download failed: {exc}")


# --------------------------------------------------------------------------
# Hardware / drive stats
# --------------------------------------------------------------------------

_cpu_sample = {}


def cpu_percent():
    """CPU utilisation since the previous call (Linux /proc/stat delta)."""
    try:
        with open("/proc/stat") as f:
            parts = [int(x) for x in f.readline().split()[1:]]
        idle = parts[3] + (parts[4] if len(parts) > 4 else 0)
        total = sum(parts)
        prev = _cpu_sample.get("stat")
        _cpu_sample["stat"] = (idle, total)
        if prev and total > prev[1]:
            return round(100 * (1 - (idle - prev[0]) / (total - prev[1])), 1)
        return None  # first sample — caller shows a placeholder once
    except (OSError, ValueError, IndexError):
        pass
    try:  # non-Linux fallback: normalised 1-minute load
        return round(min(100.0, os.getloadavg()[0] / (os.cpu_count() or 1) * 100), 1)
    except (OSError, AttributeError):
        return None


def cpu_name():
    try:
        with open("/proc/cpuinfo") as f:
            for line in f:
                if line.lower().startswith("model name"):
                    return line.split(":", 1)[1].strip()
    except OSError:
        pass
    import platform
    return platform.processor() or platform.machine() or "unknown CPU"


def mem_info():
    """Return (total_bytes, used_bytes) or (None, None)."""
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                key, _, rest = line.partition(":")
                info[key] = int(rest.strip().split()[0]) * 1024
        total = info.get("MemTotal", 0)
        avail = info.get("MemAvailable", info.get("MemFree", 0))
        return total, total - avail
    except (OSError, ValueError):
        pass
    if sys.platform == "win32":
        try:
            import ctypes

            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(stat)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            return stat.ullTotalPhys, stat.ullTotalPhys - stat.ullAvailPhys
        except (OSError, AttributeError):
            pass
    return None, None


_net_sample = {}


def net_rate():
    """Return {rx_bps, tx_bps} across all non-loopback interfaces (Linux)."""
    try:
        rx = tx = 0
        with open("/proc/net/dev") as f:
            for line in f.readlines()[2:]:
                iface, _, rest = line.partition(":")
                if iface.strip() == "lo":
                    continue
                fields = rest.split()
                rx += int(fields[0])
                tx += int(fields[8])
        now = time.time()
        prev = _net_sample.get("v")
        _net_sample["v"] = (now, rx, tx)
        if prev and now > prev[0]:
            dt = now - prev[0]
            return {"rx_bps": max(0, (rx - prev[1]) / dt),
                    "tx_bps": max(0, (tx - prev[2]) / dt)}
    except (OSError, ValueError, IndexError):
        pass
    return None


def gpu_info():
    """Return {name, util, vram_used, vram_total} or None."""
    if shutil.which("nvidia-smi"):
        try:
            proc = subprocess.run(
                ["nvidia-smi",
                 "--query-gpu=name,utilization.gpu,memory.used,memory.total",
                 "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=5)
            if proc.returncode == 0 and proc.stdout.strip():
                name, util, used, total = [
                    x.strip() for x in proc.stdout.strip().splitlines()[0].split(",")]
                return {"name": name, "util": float(util),
                        "vram_used": int(float(used)) * 1024 * 1024,
                        "vram_total": int(float(total)) * 1024 * 1024}
        except (OSError, ValueError, subprocess.TimeoutExpired, IndexError):
            pass
    try:  # AMD (amdgpu exposes utilisation via sysfs)
        for card in sorted(Path("/sys/class/drm").glob("card[0-9]")):
            busy = card / "device" / "gpu_busy_percent"
            if not busy.exists():
                continue
            util = float(busy.read_text().strip())
            vram_used = vram_total = None
            vu = card / "device" / "mem_info_vram_used"
            vt = card / "device" / "mem_info_vram_total"
            if vu.exists() and vt.exists():
                vram_used = int(vu.read_text().strip())
                vram_total = int(vt.read_text().strip())
            return {"name": "AMD GPU", "util": util,
                    "vram_used": vram_used, "vram_total": vram_total}
    except (OSError, ValueError):
        pass
    return None


def local_commit():
    try:
        proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=10)
        if proc.returncode == 0:
            return proc.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return None


# Commit the RUNNING process was started from. If an update is pulled while
# the server is running, this diverges from local_commit() until a restart —
# that's how the UI knows to offer RESTART instead of looking "fixed".
RUNNING_COMMIT = local_commit()


# --------------------------------------------------------------------------
# kiwix-serve lifecycle (mount/remount the knowledge base)
# --------------------------------------------------------------------------

def kiwix_binary():
    found = shutil.which("kiwix-serve")
    if found:
        return found
    bundled = ROOT / "tools" / "kiwix" / (
        "kiwix-serve.exe" if sys.platform == "win32" else "kiwix-serve")
    return str(bundled) if bundled.exists() else None


def restart_kiwix():
    """(Re)start kiwix-serve on port 8181 with everything in library/.

    Best-effort: used at startup, after a restart, and when a new ZIM
    finishes downloading so it mounts without any manual step.
    """
    binary = kiwix_binary()
    zims = sorted((ROOT / "library").glob("*.zim"))
    if not binary or not zims:
        return False
    try:  # stop whatever instance is currently holding port 8181
        if sys.platform == "win32":
            subprocess.run(["taskkill", "/F", "/IM", "kiwix-serve.exe"],
                           capture_output=True, timeout=10)
        else:
            # bracket stops the pattern from matching pkill's own argv
            subprocess.run(["pkill", "-f", "[k]iwix-serve"],
                           capture_output=True, timeout=10)
        time.sleep(0.5)
    except (OSError, subprocess.TimeoutExpired):
        pass
    try:
        subprocess.Popen([binary, "--port", "8181", *map(str, zims)],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                         start_new_session=True)
        clear_probe_cache()
        return True
    except OSError:
        return False


def ensure_kiwix(cfg):
    """Start kiwix-serve if ZIMs exist but nothing is serving them yet."""
    if resolve_kiwix(cfg)[0] is None:
        restart_kiwix()


# --------------------------------------------------------------------------
# Agent tools (sandboxed to the workspace directory)
# --------------------------------------------------------------------------

def safe_path(workspace, rel):
    """Resolve `rel` inside the workspace; refuse anything that escapes it."""
    candidate = (workspace / rel).resolve()
    if candidate != workspace and workspace not in candidate.parents:
        raise ValueError(f"path escapes the workspace: {rel}")
    return candidate


FILE_TOOLS = {"list_dir", "read_file", "write_file", "run_command"}
KNOWLEDGE_TOOLS = {"search_knowledge", "read_knowledge"}


def run_tool(cfg, name, args, kiwix=None):
    if name in KNOWLEDGE_TOOLS:
        if not kiwix or not kiwix[0]:
            return "error: knowledge base is not running"
        url, books = kiwix
        if name == "search_knowledge":
            results = kiwix_search(url, books, str(args.get("query", "")).strip())
            if not results:
                return "no results — try different search terms"
            lines = []
            for i, r in enumerate(results, 1):
                line = f"{i}. [{r['path']}] {r['title']}"
                if r["snippet"]:
                    line += f" — {r['snippet']}"
                lines.append(line)
            return "\n".join(lines)
        if name == "read_knowledge":
            try:
                return kiwix_read(url, str(args.get("path", "")))
            except (urllib.error.URLError, OSError, TimeoutError) as exc:
                return f"error: could not read article: {exc}"

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
        # no Content-Length on this response — tell the base class not to
        # reuse the connection or the next request would hang forever
        self.close_connection = True

    def sse(self, obj):
        self.wfile.write(f"data: {json.dumps(obj, ensure_ascii=False)}\n\n".encode("utf-8"))
        self.wfile.flush()

    # ---- routing --------------------------------------------------------

    def do_GET(self):
        path, _, query_string = self.path.partition("?")
        if path == "/api/status":
            return self.handle_status()
        if path == "/api/knowledge/search":
            return self.handle_knowledge_search(query_string)
        if path == "/api/downloads":
            return self.handle_downloads()
        if path == "/api/system":
            return self.handle_system()
        if path == "/api/updates/check":
            return self.handle_update_check()
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
            if path == "/api/downloads/start":
                return self.handle_download_start()
            if path == "/api/downloads/cancel":
                return self.handle_download_cancel()
            if path == "/api/updates/apply":
                return self.handle_update_apply()
            if path == "/api/restart":
                return self.handle_restart()
            if path == "/api/wipe":
                return self.handle_wipe()
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
        kx_url, kx_books = resolve_kiwix(cfg)
        self.send_json({
            "app": APP_NAME,
            "backend_url": url,
            "backend_kind": kind,
            "online": url is not None,
            "models": models,
            "default_model": cfg.get("default_model") or (models[0] if models else ""),
            "workspace": str(workspace_dir(cfg)),
            "kiwix_url": kx_url,
            "kiwix_online": kx_url is not None,
            "kiwix_books": kx_books,  # [{name, title}] — name keys the viewer URL
            # lets the launcher detect a stale process without touching GitHub
            "running_commit": (RUNNING_COMMIT or "")[:12],
        })

    def handle_system(self):
        du = shutil.disk_usage(ROOT)
        mem_total, mem_used = mem_info()
        self.send_json({
            "disk": {"total": du.total, "used": du.used, "free": du.free},
            "cpu": {"name": cpu_name(), "cores": os.cpu_count(),
                    "percent": cpu_percent()},
            "mem": {"total": mem_total, "used": mem_used},
            "gpu": gpu_info(),
            "net": net_rate(),
            "uptime_s": int(time.time() - SERVER_STARTED),
        })

    def handle_downloads(self):
        cfg = load_config()
        _, _, installed_models = resolve_backend(cfg)
        installed = set(installed_models)
        lib = ROOT / "library"
        models = [{**m, "installed": m["id"] in installed} for m in MODEL_CATALOG]
        zims = [{"id": z["id"], "title": z["title"], "size": z["size"],
                 "cat": z.get("cat", ""),
                 "installed": all(zim_stem_installed(lib, f)
                                  for f in z["files"])}
                for z in ZIM_CATALOG]
        with _jobs_lock:
            jobs = {k: {kk: vv for kk, vv in v.items() if kk != "cancel"}
                    for k, v in JOBS.items()}
        self.send_json({"models": models, "zims": zims, "jobs": jobs})

    def handle_download_start(self):
        body = self.read_json()
        kind, item_id = body.get("kind"), body.get("id")
        cfg = load_config()
        if kind == "model":
            if not any(m["id"] == item_id for m in MODEL_CATALOG):
                return self.send_json({"error": "unknown model"}, 400)
            backend_url, _, _ = resolve_backend(cfg)
            if backend_url is None:
                return self.send_json(
                    {"error": "model runtime is not running — start Ollama first"}, 503)
            started = start_job(f"model:{item_id}", pull_model_job,
                                backend_url, item_id)
        elif kind == "zim":
            entry = next((z for z in ZIM_CATALOG if z["id"] == item_id), None)
            if entry is None:
                return self.send_json({"error": "unknown knowledge pack"}, 400)
            started = start_job(f"zim:{item_id}", download_zim_job, entry["files"])
        else:
            return self.send_json({"error": "kind must be 'model' or 'zim'"}, 400)
        self.send_json({"ok": True, "started": started})

    def handle_download_cancel(self):
        body = self.read_json()
        job_id = body.get("job", "")
        job_update(job_id, cancel=True)
        self.send_json({"ok": True})

    def handle_wipe(self):
        """Erase runtime data. scope=chats: conversations only; scope=all:
        conversations + workspace + config, then restart fresh. Models and
        the knowledge library are never touched from here."""
        body = self.read_json()
        scope = body.get("scope")
        cfg = load_config()
        if scope == "chats":
            shutil.rmtree(conversations_dir(cfg), ignore_errors=True)
            conversations_dir(cfg)
            return self.send_json({"ok": True, "wiped": "conversations"})
        if scope == "all":
            shutil.rmtree(data_dir(cfg), ignore_errors=True)
            CONFIG_PATH.unlink(missing_ok=True)
            self.send_json({"ok": True, "wiped": "data + config",
                            "note": "restarting fresh"})

            def _re_exec():
                time.sleep(0.6)
                clear_probe_cache()
                os.execv(sys.executable,
                         [sys.executable, str(Path(__file__).resolve())])

            threading.Thread(target=_re_exec, daemon=True).start()
            return
        return self.send_json({"error": "scope must be 'chats' or 'all'"}, 400)

    def handle_restart(self):
        """Re-exec the server so freshly pulled code (or new config) loads."""
        self.send_json({"ok": True, "note": "restarting"})

        def _re_exec():
            time.sleep(0.6)
            clear_probe_cache()
            os.execv(sys.executable,
                     [sys.executable, str(Path(__file__).resolve())])

        threading.Thread(target=_re_exec, daemon=True).start()

    def handle_update_check(self):
        current = local_commit()
        result = {
            "current": (current or "")[:12] or None,
            "running": (RUNNING_COMMIT or "")[:12] or None,
            # true when a newer version is on disk but this process still
            # runs the old code (pulled while running, no restart yet)
            "restart_needed": bool(current) and bool(RUNNING_COMMIT)
                              and current != RUNNING_COMMIT,
        }
        try:
            req = urllib.request.Request(
                f"{GH_API}/repos/{GITHUB_REPO}/commits/main",
                headers={"User-Agent": "xDrive",
                         "Accept": "application/vnd.github+json"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            latest = data.get("sha", "")
            result.update({
                "online": True,
                "latest": latest[:12],
                "update_available": bool(current) and bool(latest)
                                    and latest != current,
                "latest_message": data["commit"]["message"].splitlines()[0][:100],
                "latest_date": data["commit"]["committer"]["date"][:10],
            })
        except (urllib.error.URLError, json.JSONDecodeError, KeyError,
                OSError, TimeoutError) as exc:
            result.update({"online": False,
                           "error": f"could not reach GitHub ({exc})"})
        self.send_json(result)

    def handle_update_apply(self):
        if not (ROOT / ".git").exists():
            return self.send_json({
                "ok": False,
                "output": "this copy of xDrive is not a git checkout — "
                          "re-clone the repository to enable updates"})
        try:
            proc = subprocess.run(
                ["git", "pull", "--ff-only", "origin", "main"],
                cwd=ROOT, capture_output=True, text=True, timeout=120)
            self.send_json({
                "ok": proc.returncode == 0,
                "output": (proc.stdout + proc.stderr).strip()[-2000:],
                "note": "restart xDrive to finish updating",
            })
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.send_json({"ok": False, "output": str(exc)})

    def handle_knowledge_search(self, query_string):
        cfg = load_config()
        params = urllib.parse.parse_qs(query_string)
        query = (params.get("q") or [""])[0].strip()
        if not query:
            return self.send_json({"error": "empty query"}, 400)
        kx_url, kx_books = resolve_kiwix(cfg)
        if kx_url is None:
            return self.send_json({"error": "knowledge base offline", "results": []}, 503)
        results = kiwix_search(kx_url, kx_books, query)
        self.send_json({"results": results, "viewer": kx_url})

    def handle_get_config(self):
        cfg = load_config()
        self.send_json(cfg)

    def handle_put_config(self):
        incoming = self.read_json()
        cfg = load_config()
        for key in ("backend_url", "default_model", "temperature",
                    "system_prompt", "data_dir", "max_tool_steps",
                    "command_timeout", "kiwix_url"):
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
        research_mode = bool(body.get("research_mode"))
        temperature = float(body.get("temperature", cfg.get("temperature", 0.7)))

        allowed_tools = set()
        kiwix = (None, [])
        if agent_mode:
            allowed_tools |= FILE_TOOLS
        if agent_mode or research_mode:
            kiwix = resolve_kiwix(cfg)
            if kiwix[0]:
                allowed_tools |= KNOWLEDGE_TOOLS

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
        if KNOWLEDGE_TOOLS & allowed_tools:
            system_prompt = f"{system_prompt}\n\n{KNOWLEDGE_PROMPT}"

        self.send_sse_headers()
        self.sse({"type": "meta", "conversation_id": conv["id"], "model": model})

        try:
            self.run_chat_loop(cfg, backend_url, model, temperature,
                               system_prompt, conv, allowed_tools, kiwix)
        except (BrokenPipeError, ConnectionResetError):
            save_conversation(cfg, conv)
            return
        except urllib.error.URLError as exc:
            self.sse({"type": "error", "message": f"backend error: {exc}"})
        except OSError as exc:
            self.sse({"type": "error", "message": str(exc)})
        self.sse({"type": "done"})

    def run_chat_loop(self, cfg, backend_url, model, temperature,
                      system_prompt, conv, allowed_tools, kiwix):
        """Stream a reply; when tools are allowed, execute calls and continue."""
        max_steps = int(cfg.get("max_tool_steps", 8)) if allowed_tools else 1

        for _ in range(max_steps):
            llm_messages = [{"role": "system", "content": system_prompt}]
            for msg in conv["messages"]:
                if msg["role"] == "tool":
                    llm_messages.append({
                        "role": "user",
                        "content": f"[tool result]\n{msg['content']}",
                    })
                elif msg["role"] == "assistant":
                    # Reasoning models emit <think> blocks; keep them out of
                    # the history we send back so context stays lean.
                    content = THINK_RE.sub("", msg["content"]).strip()
                    llm_messages.append({"role": "assistant", "content": content})
                else:
                    llm_messages.append({"role": msg["role"], "content": msg["content"]})

            assistant_text = ""
            for token in stream_chat(backend_url, model, llm_messages, temperature):
                assistant_text += token
                self.sse({"type": "token", "text": token})

            conv["messages"].append({"role": "assistant", "content": assistant_text})
            save_conversation(cfg, conv)

            visible_text = THINK_RE.sub("", assistant_text)
            call = extract_tool_call(visible_text) if allowed_tools else None
            if call is None:
                return

            name, args = call
            self.sse({"type": "tool_call", "name": name, "args": args})
            if name not in allowed_tools:
                result = f"error: tool '{name}' is not available in this mode"
            else:
                try:
                    result = run_tool(cfg, name, args, kiwix)
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
    ensure_kiwix(cfg)

    host = cfg.get("host", "127.0.0.1")
    port = int(os.environ.get("XDRIVE_PORT", cfg.get("port", 8484)))
    server = ThreadingHTTPServer((host, port), Handler)

    url, kind, models = resolve_backend(cfg)
    print(f"  ┌─────────────────────────────────────────────┐")
    print(f"  │  {APP_NAME} — offline AI assistant             │")
    print(f"  └─────────────────────────────────────────────┘")
    print(f"  UI:        http://{host}:{port}")
    if url:
        print(f"  LLM:       {kind} at {url} ({len(models)} model(s))")
    else:
        print(f"  LLM:       none detected — start Ollama or llama-server")
    kx_url, kx_books = resolve_kiwix(cfg)
    if kx_url:
        print(f"  Knowledge: kiwix at {kx_url} ({len(kx_books)} book(s))")
    else:
        print(f"  Knowledge: none — run scripts/pull-knowledge to add Wikipedia & docs")
    print(f"  Data:      {data_dir(cfg)}")
    print(f"  Workspace: {workspace_dir(cfg)}")
    print(f"  Press Ctrl+C to quit.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n[{APP_NAME}] bye")


if __name__ == "__main__":
    main()
