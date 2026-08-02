<div align="center">

```
██╗  ██╗██████╗ ██████╗ ██╗██╗   ██╗███████╗
╚██╗██╔╝██╔══██╗██╔══██╗██║██║   ██║██╔════╝
 ╚███╔╝ ██║  ██║██████╔╝██║██║   ██║█████╗
 ██╔██╗ ██║  ██║██╔══██╗██║╚██╗ ██╔╝██╔══╝
██╔╝╚██╗██████╔╝██║  ██║██║ ╚████╔╝ ███████╗
╚═╝  ╚═╝╚═════╝ ╚═╝  ╚═╝╚═╝  ╚═══╝  ╚══════╝
```

### The AI that lives on your hard drive.

**Code · Chat · Agent · Wikipedia — 100% local, 100% offline.**

`zero dependencies` · `arch linux + windows` · `black / white / ember orange`

</div>

---

xDrive is a self-contained AI assistant that lives entirely on one drive:
the app, the models, chat history, an agent workspace, and an offline
knowledge base with **all of English Wikipedia** and **docs for 40
programming languages & tools**. Plug the drive in, launch, and everything works —
no internet, no accounts, no cloud.

| | |
|---|---|
| 🖥 **Terminal UI** | eDEX-style cockpit: live clock, system readouts, sessions, network status, activity feed |
| 🤖 **Any local model** | auto-detects [Ollama](https://ollama.com) or [llama.cpp](https://github.com/ggerganov/llama.cpp), streams token-by-token |
| ⚒ **Agent mode** | the AI writes files and runs commands in a sandboxed workspace — it builds and tests, not just talks |
| 📚 **Knowledge base** | full Wikipedia + Arch Wiki + DevDocs served locally; the AI searches and cites them in RESEARCH mode |
| ◈ **Reasoning** | DeepSeek-R1 chain-of-thought shown as collapsible REASONING blocks |
| ⬇ **GET MORE tab** | download more models and knowledge packs from inside the app, with progress bars and resume |
| ⟳ **Updates** | one click checks GitHub for a new version and applies it |
| 🔒 **Private by design** | everything binds to `127.0.0.1`; nothing is exposed, nothing phones home |

---

## Install on Arch Linux

### 0 · Requirements

- **Hardware** — any x86-64 machine. RAM decides which models run well:

  | RAM / VRAM | Daily driver | Heavy lifter |
  |---|---|---|
  | 8 GB | `qwen2.5:3b` | `qwen2.5-coder:7b` |
  | 16 GB | `qwen2.5-coder:7b` | `qwen2.5-coder:14b` |
  | 32 GB | `qwen2.5-coder:14b` | `qwen2.5-coder:32b` / `deepseek-r1:32b` |
  | 64 GB+ | `qwen2.5-coder:32b` | `llama3.3:70b` |

- **The drive** — any big disk works (the 5TB plan is in
  [docs/MODELS.md](docs/MODELS.md)). Format it with a Linux filesystem and
  mount it, e.g.:

  ```bash
  sudo mkfs.ext4 -L xdrive /dev/sdX1        # ⚠ wipes the partition
  sudo mkdir -p /mnt/xdrive
  sudo mount /dev/sdX1 /mnt/xdrive
  sudo chown "$USER" /mnt/xdrive
  ```

### 1 · Get xDrive onto the drive

```bash
cd /mnt/xdrive
git clone https://github.com/cixpave/xDrive.git
cd xDrive
```

(Cloning with git is what enables the in-app updater.)

### 2 · One-time setup (needs internet once)

```bash
./scripts/setup-arch.sh
```

This installs and configures everything:

- `python` and `ollama` via pacman
- `python-gobject`, `gtk3`, and `webkit2gtk-4.1` — gives xDrive its own
  native application window (no browser involved)
- `kiwix-tools` (via pacman, or a static binary into `tools/kiwix/`) — serves
  the offline knowledge base
- points Ollama's model store at `models/ollama/` **on the drive** (user
  environment + systemd drop-in), so weights travel with the disk
- registers **xDrive in your application launcher** with its own icon

### 3 · Load it up (still online)

```bash
./scripts/pull-models.sh        # core model set  (~112 GB)
./scripts/pull-knowledge.sh     # Wikipedia + Arch Wiki + DevDocs  (~103 GB)
./scripts/pull-knowledge.sh --full   # optional: + Stack Overflow, Wiktionary, Wikibooks (~+180 GB)
```

Both are resumable — re-run them if a download is interrupted. You can also
skip this and use the **GET MORE** tab inside the app later.

### 4 · Launch

From then on the machine can be fully offline:

- **Application launcher** — hit Super, type “xDrive”, press Enter. It opens
  in its own window like a native app.
- **Terminal** — `./start.sh` (server in the foreground, browser tab opens).

### What starts when you launch

| Process | Port | Purpose |
|---|---|---|
| `xdrive/server.py` | `127.0.0.1:8484` | the app: UI, chat, agent tools, downloads |
| `ollama serve` | `127.0.0.1:11434` | runs the language models |
| `kiwix-serve` | `127.0.0.1:8181` | serves Wikipedia & docs from `library/` |

The launcher starts whichever of these isn't already running and wires them
together. All three bind to localhost only.

---

## Using xDrive

**Chat** — type, hit Enter. Streaming markdown, syntax-highlighted code with
COPY buttons, sessions saved on the drive in `data/conversations/`.

**RESEARCH mode** — flip the toggle and the model gains two tools:
`search_knowledge` and `read_knowledge`. It looks things up in the offline
library mid-answer and cites the articles it used. You can also search the
library yourself in the **KNOWLEDGE** panel (results open in the Kiwix
reader).

**AGENT MODE** — the model gains four more tools, confined to
`data/workspace/`:

| Tool | Does |
|---|---|
| `list_dir` / `read_file` / `write_file` | file operations in the workspace |
| `run_command` | run a shell command (timeout-guarded) |

Ask for *“a Flask app with a /health endpoint, tested”* and watch the EXEC
cards appear as it writes and runs code. Enable it only when you want it —
`run_command` executes real commands.

**Reasoning** — with a DeepSeek-R1 model selected, the model's thinking
streams into a collapsible `◈ REASONING` block. Thought text is kept out of
future context so long sessions stay fast.

**GET MORE tab** — the second tab in the terminal header:

- **SYSTEM UPDATE** — `CHECK GITHUB` compares your local commit against
  `main` on GitHub; `APPLY UPDATE` runs a fast-forward `git pull`. Restart
  xDrive afterwards.
- **MODELS** — one-click `GET` pulls any cataloged model through Ollama with
  a live progress bar.
- **KNOWLEDGE** — one-click download of Wikipedia variants (full/text-only/
  Simple), Stack Overflow, Wiktionary, Wikibooks, the Arch Wiki, and the
  DevDocs pack into `library/`. Downloads resume if interrupted — just hit
  `GET` again.

**KNOWLEDGE panel** — shows every mounted book; click one to open it in the
Kiwix reader, or hit OPEN READER for the whole library. **NETWORK panel** —
live download/upload speeds plus status of all three local services (UI,
LLM, wiki server).

**INVERT** — flips the black terminal to a white theme. **CONFIG** — backend
URL, default model, temperature, system prompt, agent limits (tool steps,
command timeout), and the knowledge base URL. The DANGER ZONE at the bottom
can **WIPE CHATS** or **FACTORY RESET** (chats + workspace + settings —
models and downloaded books always survive).

From a terminal, `./scripts/reset.sh` does the same and stops any running
processes first: add `--books` to also drop downloaded ZIMs, `--models` for
model weights, or `--everything` to get back to a fresh clone.

---

## Windows 11 — portable xDrive.exe

Windows users do not need Python, PowerShell scripts, Git, or a system-wide
Ollama installation.

1. Download the **xDrive-Windows-Portable** artifact from the latest GitHub
   Actions build and extract the complete `xDrive` folder to your hard drive.
2. Double-click **`xDrive.exe`**.
3. The first-run landing page verifies the drive, downloads portable Ollama,
   and helps you choose a starter model.

The executable always resolves storage from its own location. Conversations,
agent files, models, offline books, Edge profile/cache, and app temporary files
stay within the portable folder. Move the complete folder to a different drive
letter and launch it again—no path repair or reinstallation is needed.

The download is intentionally a portable folder containing `xDrive.exe` and
an adjacent private runtime, instead of a PyInstaller one-file build. A
one-file build extracts dependencies into the Windows temp directory, which
would violate xDrive's drive-only storage rule. See
[docs/WINDOWS-PORTABLE.md](docs/WINDOWS-PORTABLE.md) for the exact layout.

`start.bat` and `scripts/setup-windows.ps1` remain available for developers
running directly from a source checkout; end users should use `xDrive.exe`.

---

## Configuration

`config.json` (auto-created; most settings editable in-app via CONFIG):

| Key | Default | Meaning |
|---|---|---|
| `backend_url` | `auto` | `auto` probes Ollama (11434) then llama.cpp (8080) |
| `default_model` | first available | model preselected in the UI |
| `temperature` | `0.7` | sampling temperature |
| `system_prompt` | built-in | assistant personality |
| `data_dir` | `data` | conversations + agent workspace |
| `max_tool_steps` | `8` | agent/research iteration cap per message |
| `command_timeout` | `120` | seconds before a command is killed |
| `kiwix_url` | `auto` | knowledge base URL (`auto` probes port 8181) |
| `port` | `8484` | UI port (or env `XDRIVE_PORT`) |

## Troubleshooting (Arch)

| Symptom | Fix |
|---|---|
| “NO LLM RUNTIME DETECTED” | `ollama serve` isn't running — `systemctl start ollama` or just relaunch xDrive; click **LINK** in the SYSTEM panel to rescan |
| Models downloading to `~/.ollama` instead of the drive | log out/in after setup (it sets `OLLAMA_MODELS` via `environment.d`), or `export OLLAMA_MODELS=/mnt/xdrive/xDrive/models/ollama` |
| KNOWLEDGE panel says OFFLINE | no ZIMs in `library/` yet, or kiwix-serve isn't running — relaunch xDrive after downloading |
| Port 8484 already in use | `XDRIVE_PORT=9090 ./start.sh` |
| Launcher entry missing after moving the drive | `./scripts/install-desktop.sh` (it stores the absolute path) |
| Opens in a browser instead of its own window | `sudo pacman -S --needed webkit2gtk-4.1 python-gobject gtk3`, then relaunch |
| APPLY UPDATE fails | local changes on the drive: `git stash && git pull --ff-only origin main` inside the repo |
| Updated but nothing changed / repeated `/api/system` 404s in the console | an old server process is still running. Relaunching from the app launcher now detects and replaces it automatically; otherwise hit **RESTART** (bottom-left) or `pkill -f xdrive/server.py` |
| Downloaded knowledge doesn't show in KNOWLEDGE panel | new ZIMs auto-mount after download; if BOOKS stays 0, hit **RESTART** |

## Project layout

```
xdrive/server.py   the entire backend — one file, Python stdlib only
xdrive/window.py   native GTK/WebKit app window
xdrive/desktop.py  packaged Windows desktop entry point
xdrive/paths.py    drive-relative storage and portable environment
xdrive/portable_runtime.py  portable Ollama + Edge launcher
web/               terminal UI (vanilla JS + bundled marked/highlight)
.github/workflows/build-windows.yml  produces xDrive-Windows-Portable.zip
scripts/           setup, model/knowledge downloads, desktop-entry install
assets/            app icon
docs/MODELS.md     the 5TB drive plan
start.sh           Linux launcher (--app = desktop-app mode)
start.bat          Windows launcher
data/       ← runtime: conversations + agent workspace
models/     ← setup:   model weights
library/    ← setup:   Wikipedia + docs ZIMs
tools/      ← setup:   kiwix-serve binary (if not system-wide)
```
