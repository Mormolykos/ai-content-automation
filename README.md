# AI Content Automation Pipeline

A daily, self-running content-automation system built on the open-source AI stack used
in production teams: **n8n + LangChain + LangGraph + FastAPI**.

It turns a folder of images into validated, SEO-optimised, ready-to-publish content
packages — one per day — for **The Mirelands**, a dark-fantasy franchise (ebooks,
dramatized audiobooks, and a browser game).

---

## What it does

1. **n8n** (self-hosted in Docker) fires on a daily schedule.
2. It calls a **decoupled FastAPI service** over HTTP — `host.docker.internal:8090/run` —
   so the orchestrator never needs to know how the pipeline is implemented.
3. The service runs a **LangGraph** state machine:
   `pick → caption → validate → (retry if invalid) → save`.
4. **Captioning** uses a **multimodal LLM** (Google Gemini): it *sees* the image and
   returns structured metadata (title, description, 8–12 tags, alt-text), enforced by a
   **Pydantic** schema via LangChain's `with_structured_output`.
5. **Validation** checks length / keyword / tag rules; on failure the graph **loops back**
   and regenerates (up to 3 attempts).
6. Per-folder context files keep names and lore accurate (no hallucination); per-folder
   link overrides deep-link each item to the right landing page.

---

## Architecture

```text
┌───────────── Docker ──────────────┐        ┌──────────── Host ────────────┐
│  n8n  (Schedule Trigger, :5678)    │  HTTP  │  FastAPI  (api.py, :8090)    │
│   └─ HTTP Request ─────────────────┼───────▶│   POST /run                  │
└────────────────────────────────────┘        │     │                        │
   host.docker.internal:8090/run               │     ▼                        │
                                               │  LangGraph (pin_graph.py)    │
                                               │   pick → caption →           │
                                               │   validate ──fail──┐         │
                                               │     │ ok           │ (retry) │
                                               │     ▼              │         │
                                               │   save  ◀──────────┘         │
                                               └──────────────────────────────┘
```

**Why a graph, not a function?** The retry edge. A linear script can't cleanly say "if the
result fails my rules, go back a step and try again." LangGraph's conditional edge makes
that a first-class part of the flow.

**Why a separate FastAPI service?** n8n runs in Docker and can't execute host Python
directly. Exposing the pipeline over HTTP keeps the orchestrator and the engine fully
decoupled — either side can change without touching the other.

---

## Stack

| Layer | Tech |
|---|---|
| Orchestration / scheduling | n8n (self-hosted, Docker) |
| Service bridge | FastAPI + Uvicorn |
| Pipeline / state machine | LangGraph |
| LLM call + structured output | LangChain + Pydantic |
| Model | Google Gemini (multimodal) |

---

## Project layout

```text
automation/
├── langchain/
│   ├── generate_pin.py   # pick an image → multimodal caption → save (LangChain + Gemini)
│   ├── pin_graph.py      # LangGraph state machine: pick → caption → validate → retry → save
│   └── api.py            # FastAPI wrapper exposing POST /run (the n8n bridge)
├── n8n/
│   └── docker-compose.yml
├── requirements.txt
├── .env.example
└── README.md
```

---

## Quick start

### 1. Install

```bash
python -m venv .venv
# Windows:        .venv\Scripts\activate
# macOS / Linux:  source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure

```bash
cp .env.example .env
# edit .env and add your GEMINI_API_KEY  (free tier works: https://aistudio.google.com/apikey)
```

### 3. Run the pipeline once

```bash
python langchain/pin_graph.py
```

Output is written to `outputs/pin_<timestamp>.json`.

### 4. Run it as a service (what n8n calls)

```bash
python langchain/api.py          # serves http://0.0.0.0:8090  (interactive docs at /docs)
curl -X POST http://localhost:8090/run
```

### 5. Schedule it with n8n

```bash
cd n8n
docker compose up -d             # n8n at http://localhost:5678
```

In n8n: **Schedule Trigger → HTTP Request** (`POST http://host.docker.internal:8090/run`).
Publish the workflow and it runs daily.

---

## Anti-hallucination

A per-folder `_context.txt` supplies author-authored facts the model must respect (e.g.
*"Dariah is a young orc shaman who wields two throwing axes"*). Without it, the model is
instructed to describe **only what is visible** and invent no names, places, or events.
A per-folder `_link.txt` overrides the default backlink so each item deep-links correctly.

---

## Output example

```json
{
  "folder": "kthonia",
  "link": "https://tts.bedvibe.studio/the-mirelands/kthonia/",
  "valid": true,
  "attempts": 1,
  "metadata": {
    "title": "Dark fantasy map of Kthonia in The Mirelands: spired city, turbulent ocean, mystic geysers",
    "description": "Journey into Kthonia, a realm within The Mirelands ...",
    "tags": ["the mirelands", "kthonia", "dark fantasy", "fantasy map", "..."],
    "alt_text": "An aerial fantasy map of a spired island city beside a turbulent ocean."
  }
}
```

---

## License

Provided as a public portfolio / proof-of-work reference. © 2026 Panagiotis Gkilis.
