# Model guide — filling a 5TB drive well

xDrive talks to any local runtime that speaks the OpenAI chat API. The easiest
is **Ollama**; **llama.cpp** (`llama-server`) also works out of the box.

All model weights live on this drive in `models/ollama/` (the setup scripts
point `OLLAMA_MODELS` there), so the whole thing — app, models,
conversations, workspace — travels with the drive.

## Core set (~90 GB) — pulled by `scripts/pull-models.sh` / `.ps1`

| Model | Size | Use it for |
|---|---|---|
| `qwen2.5-coder:14b` | ~9 GB | Everyday coding: writing, debugging, refactoring |
| `qwen2.5:14b` | ~9 GB | Everyday general chat, writing, Q&A |
| `qwen2.5-coder:32b` | ~20 GB | Hard coding problems (needs ~24 GB RAM/VRAM) |
| `llama3.3:70b` | ~43 GB | Best general reasoning (needs ~48 GB RAM, or 64 GB system RAM on CPU) |
| `qwen2.5:3b` | ~2 GB | Instant answers on weak hardware / battery |

## Worth adding if you have the RAM (~250 GB more)

| Model | Size | Notes |
|---|---|---|
| `deepseek-r1:32b` | ~20 GB | Strong step-by-step reasoning (math, logic, planning) |
| `deepseek-r1:70b` | ~43 GB | Heavier reasoning variant |
| `qwen2.5-coder:7b` | ~5 GB | Fast autocomplete-grade coding |
| `llava:13b` | ~8 GB | Vision — describe screenshots and images |
| `mixtral:8x22b` | ~80 GB | Large mixture-of-experts generalist |
| `command-r-plus:104b` | ~59 GB | Long-context RAG / document work |

## Filling out the rest of 5 TB

Weights are the small part; a good offline setup also carries the knowledge
you'd otherwise google:

- **Full-precision GGUFs** — pull `q8_0` or `fp16` variants of your favorite
  models for maximum quality (`ollama pull qwen2.5-coder:32b-instruct-q8_0`).
  A 70B fp16 is ~140 GB.
- **Offline docs** — [Kiwix](https://kiwix.org) ZIM files: all of Wikipedia
  (~100 GB), Stack Overflow (~75 GB), DevDocs, Arch Wiki. Put them in
  `docs-offline/`.
- **Package mirrors** — a pacman mirror snapshot and a Python wheelhouse
  (`pip download`) so you can install software offline.
- **Your code and data** — the agent workspace (`data/workspace/`) and any
  repos you want the assistant to work on.

Suggested drive layout:

```
xDrive/
├── xdrive/          the app
├── web/             the UI
├── models/ollama/   model weights            (~0.3–2 TB)
├── docs-offline/    Kiwix ZIMs, DevDocs      (~0.3 TB)
├── mirrors/         pacman / pip mirrors     (~0.5 TB)
└── data/            conversations + agent workspace
```

## Sizing to your hardware

| Your RAM / VRAM | Daily driver | Heavy lifter |
|---|---|---|
| 8 GB | `qwen2.5:3b` | `qwen2.5-coder:7b` |
| 16 GB | `qwen2.5-coder:7b` | `qwen2.5-coder:14b` |
| 32 GB | `qwen2.5-coder:14b` | `qwen2.5-coder:32b` |
| 64 GB+ | `qwen2.5-coder:32b` | `llama3.3:70b` |

Rule of thumb: a `qN` quant needs roughly `parameters × N / 8` bytes of
memory, plus a little for context.

## Using llama.cpp instead of Ollama

xDrive auto-detects `llama-server` on port 8080:

```bash
llama-server -m models/gguf/qwen2.5-coder-14b-q4_k_m.gguf -c 8192 --port 8080
```

Keep raw GGUF files in `models/gguf/`. On Arch: `sudo pacman -S llama.cpp`;
on Windows: download a release zip from the llama.cpp GitHub page once and
keep it on the drive.
