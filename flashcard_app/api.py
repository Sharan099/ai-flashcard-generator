import logging
import shutil
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Request, Response, UploadFile
from fastapi.responses import HTMLResponse

from flashcard_app.generator import generate_flashcards
from flashcard_app.ocr_service import extract_text_from_pdf
from flashcard_app.storage import (
    delete_source,
    list_sources,
    load_flashcards,
    move_card_to_known,
    save_flashcards,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)

NOTES_DIR = Path("notes")
NOTES_DIR.mkdir(exist_ok=True)


def get_session_id(request: Request, response: Response) -> str:
    """Read the visitor's session id from their cookie, or create a new one."""
    session_id = request.cookies.get("session_id")
    if not session_id:
        session_id = str(uuid.uuid4())
        response.set_cookie(
            key="session_id",
            value=session_id,
            httponly=True,
            max_age=60 * 60 * 24 * 30,  # remember for 30 days
        )
        logger.info("New visitor — created session %s", session_id)
    return session_id


def flashcards_path(session_id: str) -> str:
    return str(DATA_DIR / f"{session_id}_flashcards.json")


def known_path(session_id: str) -> str:
    return str(DATA_DIR / f"{session_id}_known.json")


def session_notes_dir(session_id: str) -> Path:
    path = NOTES_DIR / session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> str:
    html_path = Path("flashcard_app/static/index.html")
    return html_path.read_text(encoding="utf-8")


@app.get("/api/flashcards")
async def get_flashcards(request: Request, response: Response) -> list[dict]:
    session_id = get_session_id(request, response)
    cards = load_flashcards(flashcards_path(session_id))
    return [card.to_dict() for card in cards]


@app.post("/api/upload")
async def upload_pdf(request: Request, response: Response, file: UploadFile = File(...)) -> dict:
    session_id = get_session_id(request, response)

    save_dir = session_notes_dir(session_id)
    save_path = save_dir / file.filename
    with save_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info("Session %s uploaded: %s", session_id, file.filename)

    text = extract_text_from_pdf(str(save_path))
    new_cards = await generate_flashcards(text, source=file.filename)

    fpath = flashcards_path(session_id)
    existing_cards = load_flashcards(fpath)
    all_cards = existing_cards + new_cards
    save_flashcards(all_cards, fpath)

    return {
        "filename": file.filename,
        "new_cards_count": len(new_cards),
        "total_cards": len(all_cards),
    }


@app.get("/api/sources")
async def get_sources(request: Request, response: Response) -> list[dict]:
    session_id = get_session_id(request, response)
    cards = load_flashcards(flashcards_path(session_id))
    return list_sources(cards)


@app.delete("/api/sources/{source_name}")
async def remove_source(source_name: str, request: Request, response: Response) -> dict:
    session_id = get_session_id(request, response)
    remaining = delete_source(source_name, flashcards_path(session_id))

    pdf_path = session_notes_dir(session_id) / source_name
    if pdf_path.exists():
        pdf_path.unlink()
        logger.info("Deleted file: %s", pdf_path)

    return {"deleted_source": source_name, "remaining_cards": len(remaining)}


@app.get("/api/known")
async def get_known_cards(request: Request, response: Response) -> list[dict]:
    session_id = get_session_id(request, response)
    cards = load_flashcards(known_path(session_id))
    return [card.to_dict() for card in cards]


@app.post("/api/known/{card_id}")
async def mark_known(card_id: str, request: Request, response: Response) -> dict:
    session_id = get_session_id(request, response)
    move_card_to_known(card_id, flashcards_path(session_id), known_path(session_id))
    return {"moved_card_id": card_id}