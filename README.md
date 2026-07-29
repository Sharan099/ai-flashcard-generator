# StudyDeck — AI Flashcard Generator

Turn a PDF of notes (typed or scanned) into study flashcards automatically, using a **local LLM** — no API key, no cost, runs entirely on your own machine.

Upload a PDF → OCR/text extraction → local LLM generates question/answer pairs → flip-card study UI in the browser, with per-source management and a separate "known cards" deck.

## Why this project

Most "AI wrapper" tutorials call a cloud API and stop there. This project is built the other way around: a real backend architecture (OOP models, async I/O, typing, logging, clean separation of concerns) with a local AI model as one interchangeable component — not the whole point. The goal was to understand *how* an AI-powered application is actually engineered, not just to call an API.

## Features

- **PDF ingestion** — extracts native text where available, falls back to OCR (Tesseract) for scanned/handwritten pages
- **Local LLM generation** (Ollama + Llama 3.2) — no API key required, fully offline
- **Format-agnostic parsing** — detects pre-structured Q&A instantly (no LLM call needed) and only uses the LLM for freeform notes, tables, or narrative text
- **Structured output enforcement** — uses Ollama's JSON-schema-constrained generation, with a regex fallback for resilience
- **Flip-card study UI** — served directly from the same backend, source-management sidebar, and a separate "known" deck
- **Concurrent + sequential async processing** — chunks processed concurrently where safe, sequentially where the local model is the bottleneck (see [Architecture notes](#architecture-notes))

## Architecture

```
Browser (index.html)
      │  fetch() calls
      ▼
FastAPI (api.py)  ───────────────────────────┐
      │                                      │
      ▼                                      ▼
ocr_service.py                        generator.py
(PyMuPDF + Tesseract OCR)             (routes: structured fast-path
      │                                or LLM path, chunks text)
      │                                      │
      └──────────────┬───────────────────────┘
                      ▼
               ai_service.py
        (Ollama local LLM calls,
         schema-constrained JSON output)
                      │
                      ▼
                storage.py
        (JSON persistence: flashcards.json,
              known_cards.json)
                      │
                      ▼
                models.py
           (Flashcard dataclass)
```

Each module has exactly one responsibility. `main.py`/`api.py` never contain business logic — they only orchestrate calls between modules. Swapping the AI provider (e.g. from Ollama to a cloud API) only requires editing `ai_service.py`; nothing else in the codebase needs to change.

## Tech stack

| Layer | Tool |
|---|---|
| Language | Python 3.13 |
| Package/env management | `uv` |
| Web framework | FastAPI + Uvicorn |
| PDF text extraction | PyMuPDF (`fitz`) |
| OCR | Tesseract (`pytesseract`) |
| Local LLM | Ollama (`llama3.2:3b`) |
| HTTP client (async) | `httpx` |
| Frontend | Vanilla HTML/CSS/JS (no framework) |
| Data storage | Flat JSON files |

## Concepts applied

- **OOP** — `Flashcard` dataclass with constructors, instance/class methods (`to_dict`/`from_dict`), encapsulation
- **Typing** — full type hints across all modules (`list[Flashcard]`, `Optional`, etc.)
- **Logging** — structured logging throughout, replacing `print()`, with levels used deliberately
- **Async programming** — `async`/`await`, `asyncio.gather` for genuinely parallel I/O, sequential `await` in a loop where the backend (local LLM) is a serial bottleneck — a deliberate, reasoned choice, not a default
- **Packaging** — proper Python package structure (`flashcard_app/`), dependencies managed via `pyproject.toml`
- **Clean architecture** — strict separation between OCR, AI generation, storage, and orchestration layers

## Setup

### Prerequisites
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- [Ollama](https://ollama.com/) installed, with a model pulled: `ollama pull llama3.2:3b`
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) installed (for scanned/handwritten PDFs)

### Install and run

```bash
git clone https://github.com/YOUR_USERNAME/ai-flashcard-generator.git
cd ai-flashcard-generator
uv venv
.venv\Scripts\activate      # Windows
uv sync
uv run uvicorn flashcard_app.api:app --reload
```

Open `http://127.0.0.1:8000` in your browser.

## Project structure

```
flashcard_app/
    models.py          # Flashcard dataclass
    ocr_service.py      # PDF text extraction + OCR
    ai_service.py        # Local LLM calls, structured output
    generator.py          # Routing logic: structured fast-path vs LLM path
    storage.py             # JSON persistence, source management, known deck
    api.py                   # FastAPI routes, orchestration only
    static/
        index.html            # Flip-card UI
main.py                        # CLI entry point (terminal-only mode)
pyproject.toml
README.md
```

## Known limitations

- Small local models (3B parameters) are less reliable at following formatting instructions than large cloud models — mitigated with schema-constrained output and a regex fallback, but not 100% eliminated
- OCR quality on genuinely messy handwriting is limited by Tesseract itself, not by this app's logic
- No authentication/multi-user support — designed for local, single-user use

## What I'd build next

- Retrieval-augmented generation (RAG) using embeddings + a vector database, to answer questions about the uploaded notes directly
- Automated tests (`pytest`) for the generator/storage logic
- Dockerized deployment