import logging
import shutil
from pathlib import Path

from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from flashcard_app.generator import generate_flashcards
from flashcard_app.ocr_service import extract_text_from_pdf
from flashcard_app.storage import load_flashcards, save_flashcards, list_sources, delete_source, move_card_to_known

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

app = FastAPI()

UPLOAD_DIR = Path("notes")
UPLOAD_DIR.mkdir(exist_ok=True)


@app.get("/", response_class=HTMLResponse)
async def serve_ui() -> str:
    """Serve the main flip-card HTML page."""
    html_path = Path("flashcard_app/static/index.html")
    return html_path.read_text(encoding="utf-8")


@app.get("/api/flashcards")
async def get_flashcards() -> list[dict]:
    """Return all saved flashcards as JSON."""
    cards = load_flashcards()
    return [card.to_dict() for card in cards]


@app.post("/api/upload")
async def upload_pdf(file: UploadFile = File(...)) -> dict:
    """Accept a PDF upload, run OCR/extraction, generate flashcards, save them."""
    save_path = UPLOAD_DIR / file.filename
    with save_path.open("wb") as f:
        shutil.copyfileobj(file.file, f)

    logger.info("Received upload: %s", file.filename)

    text = extract_text_from_pdf(str(save_path))
    new_cards = await generate_flashcards(text,source=file.filename)

    existing_cards = load_flashcards()
    all_cards = existing_cards + new_cards
    save_flashcards(all_cards)

    return {
        "filename": file.filename,
        "new_cards_count": len(new_cards),
        "total_cards": len(all_cards),
    }

@app.get("/api/sources")
async def get_sources() -> list[dict]:
    """List all uploaded sources with how many flashcards came from each."""
    cards = load_flashcards()
    return list_sources(cards)


@app.delete("/api/sources/{source_name}")
async def remove_source(source_name: str) -> dict:
    """Delete all flashcards from a given source, and delete the PDF file itself."""
    remaining = delete_source(source_name)

    pdf_path = UPLOAD_DIR / source_name
    if pdf_path.exists():
        pdf_path.unlink()
        logger.info("Deleted file: %s", pdf_path)

    return {"deleted_source": source_name, "remaining_cards": len(remaining)}


@app.get("/api/known")
async def get_known_cards() -> list[dict]:
    """Return all cards in the known deck."""
    cards = load_flashcards("known_cards.json")
    return [card.to_dict() for card in cards]


@app.post("/api/known/{card_id}")
async def mark_known(card_id: str) -> dict:
    """Move a specific flashcard (by id) into the known deck."""
    move_card_to_known(card_id)
    return {"moved_card_id": card_id}