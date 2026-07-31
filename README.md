# Ember — your offline AI assistant

<p align="center"><strong>Code · Chat · Agent — 100% local, 100% offline.</strong></p>

Ember is a self-contained AI assistant that lives entirely on your hard
drive. It handles coding tasks and general questions, runs on **Arch Linux**
and **Windows**, and needs **no internet** once models are downloaded — a
modern black & white interface with an ember-orange accent.

- **Zero dependencies** — the app is pure Python standard library + vanilla
  JS. If you have Python 3.8+, it runs. No pip, no node, no build step.
- **Any local model** — auto-detects [Ollama](https://ollama.com) or
  [llama.cpp](https://github.com/ggerganov/llama.cpp) (`llama-server`) and
  streams responses token by token.
- **Agent mode for coding** — the model can list, read, and write files and
  run commands inside a sandboxed workspace on the drive, so it can actually
  build and test things, not just talk about them.
- **Everything on the drive** — model weights, conversations, settings, and
  the agent workspace all live alongside the app, so the whole assistant
  travels with your 5TB drive.
- **Dark & light themes** — black-first design with a white theme one click
  away; orange accent throughout.

## Quick start

### Arch Linux

```bash
./scripts/setup-arch.sh    # one-time: installs python + ollama (needs internet)
./scripts/pull-models.sh   # one-time: downloads the core model set (~90 GB)
./start.sh                 # every time after: fully offline
```

### Windows

```powershell
powershell -ExecutionPolicy Bypass -File scripts\setup-windows.ps1   # one-time
powershell -ExecutionPolicy Bypass -File scripts\pull-models.ps1     # one-time
```

then just double-click **`start.bat`**.

The UI opens at [http://127.0.0.1:8484](http://127.0.0.1:8484).

## How it works

```
┌──────────────┐   SSE stream    ┌───────────────┐   OpenAI API   ┌──────────────┐
│  Web UI      │ ◄────────────── │ ember/server  │ ◄────────────► │ Ollama or    │
│  (black/     │ ──────────────► │  (Python      │                │ llama-server │
│  white/      │    fetch        │   stdlib)     │                │  + models on │
│  orange)     │                 │               │                │  this drive  │
└──────────────┘                 └──────┬────────┘                └──────────────┘
                                        │
                              data/conversations/  (chat history, JSON)
                              data/workspace/      (agent sandbox)
```

Everything binds to `127.0.0.1` only — nothing is exposed to the network.

## Agent mode

Flip the **Agent mode** toggle and the model gains four tools, all confined
to `data/workspace/` on the drive:

| Tool | What it does |
|---|---|
| `list_dir` | list a directory |
| `read_file` | read a text file |
| `write_file` | create or overwrite a file |
| `run_command` | run a shell command (with a timeout) |

Ask it to *"create a Flask app with a /health endpoint and test it"* and
watch it write the files and run them. Tool activity shows up as expandable
cards in the chat. Only enable it when you want it — `run_command` executes
real commands on your machine.

## Models

`scripts/pull-models.*` grabs a balanced core set (coding + general +
lightweight, ~90 GB). See **[docs/MODELS.md](docs/MODELS.md)** for the full
5TB drive plan — bigger quants, reasoning and vision models, and offline
documentation (Wikipedia, Stack Overflow) to pair with it.

## Configuration

Settings live in `config.json` (auto-created on first run) and most can be
changed from the ⚙ settings panel in the UI:

| Key | Default | Meaning |
|---|---|---|
| `backend_url` | `auto` | `auto` probes Ollama (11434) then llama.cpp (8080); or set an explicit URL |
| `default_model` | first available | model preselected in the UI |
| `temperature` | `0.7` | sampling temperature |
| `system_prompt` | built-in | assistant personality/instructions |
| `data_dir` | `data` | where conversations + workspace live |
| `max_tool_steps` | `8` | agent-mode iteration cap per message |
| `command_timeout` | `120` | seconds before a command is killed |
| `port` | `8484` | UI port (or set `EMBER_PORT`) |

## Project layout

```
ember/server.py   the entire backend (single file, stdlib only)
web/              the UI (index.html, style.css, app.js, bundled libs)
scripts/          one-time setup + model download for Arch and Windows
docs/MODELS.md    model recommendations for a 5TB drive
start.sh          launcher (Linux)
start.bat         launcher (Windows)
data/             created at runtime: conversations + agent workspace
models/           created by setup: model weights (kept on the drive)
```
