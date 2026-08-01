# xDrive — offline AI terminal

<p align="center"><strong>Code · Chat · Agent — 100% local, 100% offline.</strong></p>

xDrive is a self-contained AI assistant that lives entirely on your hard
drive. It handles coding tasks and general questions, runs on **Arch Linux**
and **Windows**, and needs **no internet** once models are downloaded — a
hacker/terminal interface in black & white with a Claude-orange accent:
live clock, system readouts, session list, network status, and an activity
feed around a central AI terminal.

- **Zero dependencies** — the app is pure Python standard library + vanilla
  JS. If you have Python 3.8+, it runs. No pip, no node, no build step.
- **Any local model** — auto-detects [Ollama](https://ollama.com) or
  [llama.cpp](https://github.com/ggerganov/llama.cpp) (`llama-server`) and
  streams responses token by token.
- **Agent mode for coding** — the model can list, read, and write files and
  run commands inside a sandboxed workspace on the drive, so it can actually
  build and test things, not just talk about them.
- **Built-in knowledge base** — all of English Wikipedia, the Arch Wiki, and
  documentation for ~17 programming languages/tools live on the drive as ZIM
  files. The AI can search and read them (RESEARCH mode), and you can search
  them yourself from the KNOWLEDGE panel.
- **Reasoning models** — DeepSeek-R1 ships in the core set; its chain of
  thought renders as collapsible REASONING blocks in the terminal.
- **Everything on the drive** — model weights, conversations, settings, and
  the agent workspace all live alongside the app, so the whole assistant
  travels with your 5TB drive.
- **INVERT** — black terminal by default; one click flips to a white theme.

## Quick start

### Arch Linux

```bash
./scripts/setup-arch.sh       # one-time: installs python + ollama + kiwix (needs internet)
./scripts/pull-models.sh      # one-time: downloads the core model set (~112 GB)
./scripts/pull-knowledge.sh   # one-time: downloads Wikipedia + code docs (~103 GB)
./start.sh                    # every time after: fully offline
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1     # one-time
powershell -ExecutionPolicy Bypass -File scripts\pull-models.ps1       # one-time
powershell -ExecutionPolicy Bypass -File scripts\pull-knowledge.ps1    # one-time
```

then just double-click **`start.bat`**.

The UI opens at [http://127.0.0.1:8484](http://127.0.0.1:8484).

## Desktop app (Arch / Linux)

`setup-arch.sh` registers xDrive in your application launcher automatically.
To (re)install the entry by hand:

```bash
./scripts/install-desktop.sh            # add/update launcher entry + icon
./scripts/install-desktop.sh --remove   # uninstall
```

After that, **xDrive** shows up in GNOME/KDE/rofi/wofi like any other app,
with its own terminal-style icon. Launching it starts the server, Ollama,
and the knowledge base in the background, then opens xDrive in its own
window (Chromium app mode when available, otherwise your default browser).
The entry stores the drive's absolute path — if you mount the drive at a
different location, re-run the install script once.

## How it works

```
┌──────────────┐   SSE stream    ┌────────────────┐   OpenAI API   ┌──────────────┐
│  Terminal UI │ ◄────────────── │ xdrive/server  │ ◄────────────► │ Ollama or    │
│  (black/     │ ──────────────► │  (Python       │                │ llama-server │
│  white/      │    fetch        │   stdlib)      │                │  + models on │
│  orange)     │                 │                │                │  this drive  │
└──────────────┘                 └──────┬─────────┘                └──────────────┘
                                        │
                              data/conversations/  (chat history, JSON)
                              data/workspace/      (agent sandbox)
```

Everything binds to `127.0.0.1` only — nothing is exposed to the network.

## Agent mode

Flip the **AGENT MODE** toggle in the MODEL panel and the model gains four
tools, all confined to `data/workspace/` on the drive:

| Tool | What it does |
|---|---|
| `list_dir` | list a directory |
| `read_file` | read a text file |
| `write_file` | create or overwrite a file |
| `run_command` | run a shell command (with a timeout) |

Ask it to *"create a Flask app with a /health endpoint and test it"* and
watch it write the files and run them. Tool executions show up as expandable
`EXEC` cards in the terminal and in the ACTIVITY feed. Only enable it when
you want it — `run_command` executes real commands on your machine.

## Knowledge base (offline Wikipedia + code docs)

`scripts/pull-knowledge.*` fills `library/` with ZIM archives served locally
by [kiwix-serve](https://kiwix.org) (installed by the setup script, started
automatically by the launchers):

- **All of English Wikipedia** with images (~102 GB)
- **Arch Wiki**
- **DevDocs** for Python, JavaScript, TypeScript, Node, HTML, CSS, C, C++,
  Rust, Go, Java, Bash, Git, Docker, PostgreSQL, React, Rails
- `--full` / `-Full` adds **all of Stack Overflow** (~75 GB), Wiktionary,
  and Wikibooks

Two ways to use it, both fully offline:

1. **RESEARCH toggle** — the model gets `search_knowledge` and
   `read_knowledge` tools, looks up articles mid-answer, and cites them.
   (AGENT MODE includes these tools too.)
2. **KNOWLEDGE panel** — type a query in the right-hand panel to search the
   library yourself; results open in the Kiwix reader.

## Reasoning

The core model set includes **DeepSeek-R1** (14B and 32B). When a reasoning
model thinks before answering, xDrive shows the chain of thought as a
collapsed `REASONING` block — open it to watch the model work. Reasoning
text is kept out of the context sent back to the model on later turns, so
long sessions stay fast.

## Models

`scripts/pull-models.*` grabs a balanced core set (coding + general +
lightweight + reasoning, ~112 GB). See **[docs/MODELS.md](docs/MODELS.md)** for the full
5TB drive plan — bigger quants, reasoning and vision models, and offline
documentation (Wikipedia, Stack Overflow) to pair with it.

## Configuration

Settings live in `config.json` (auto-created on first run) and most can be
changed from the CONFIG panel in the UI:

| Key | Default | Meaning |
|---|---|---|
| `backend_url` | `auto` | `auto` probes Ollama (11434) then llama.cpp (8080); or set an explicit URL |
| `default_model` | first available | model preselected in the UI |
| `temperature` | `0.7` | sampling temperature |
| `system_prompt` | built-in | assistant personality/instructions |
| `data_dir` | `data` | where conversations + workspace live |
| `max_tool_steps` | `8` | agent-mode iteration cap per message |
| `command_timeout` | `120` | seconds before a command is killed |
| `kiwix_url` | `auto` | knowledge base URL; `auto` probes kiwix-serve on 8181 |
| `port` | `8484` | UI port (or set `XDRIVE_PORT`) |

## Project layout

```
xdrive/server.py  the entire backend (single file, stdlib only)
web/              the terminal UI (index.html, style.css, app.js, bundled libs)
scripts/          one-time setup + model download for Arch and Windows
docs/MODELS.md    model recommendations for a 5TB drive
start.sh          launcher (Linux; --app for desktop-app mode)
assets/           app icon (SVG)
start.bat         launcher (Windows)
data/             created at runtime: conversations + agent workspace
models/           created by setup: model weights (kept on the drive)
library/          created by setup: Wikipedia + docs ZIM files
tools/            kiwix-serve binary if not installed system-wide
```
