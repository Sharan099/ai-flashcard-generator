import json 
import logging
from pathlib import Path

from flashcard_app.models import Flashcard
logger = logging.getLogger(__name__)

def save_flashcards(cards: list[Flashcard], filepath: str ="flashcards.json") -> None:
    path = Path(filepath)
    data = [card.to_dict() for card in cards]

    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)

    logger.info("Saved %d flashcards to %s", len(cards), filepath)


def load_flashcards(filepath: str = "flashcards.json") -> list[Flashcard]:
    """Load flashcards from a JSON file. Returns empty list if file doesn't exist."""
    path = Path(filepath)

    if not path.exists():
        logger.warning("No existing flashcard file found at %s", filepath)
        return []

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    cards = [Flashcard.from_dict(item) for item in data]
    logger.info("Loaded %d flashcards from %s", len(cards), filepath)
    return cards



def list_sources(cards: list[Flashcard]) -> list[dict]:
    """Summarize how many flashcards came from each source (PDF filename)."""
    counts: dict[str, int] = {}
    for card in cards:
        counts[card.source] = counts.get(card.source, 0) + 1
    return [{"source": name, "count": count} for name, count in counts.items()]


def delete_source(source_name: str, filepath: str = "flashcards.json") -> list[Flashcard]:
    """Remove all flashcards that came from a given source, save, and return the remaining list."""
    cards = load_flashcards(filepath)
    remaining = [c for c in cards if c.source != source_name]
    save_flashcards(remaining, filepath)
    logger.info("Deleted source '%s' — removed %d card(s)", source_name, len(cards) - len(remaining))
    return remaining


def move_card_to_known(card_id: str, main_filepath: str = "flashcards.json", known_filepath: str = "known_cards.json") -> None:
    """Move one flashcard (by id) from the main deck into the known-cards deck."""
    main_cards = load_flashcards(main_filepath)
    known_cards = load_flashcards(known_filepath)

    card_to_move = next((c for c in main_cards if c.id == card_id), None)
    if card_to_move is None:
        logger.warning("Card id %s not found, nothing moved", card_id)
        return

    remaining_main = [c for c in main_cards if c.id != card_id]
    known_cards.append(card_to_move)

    save_flashcards(remaining_main, main_filepath)
    save_flashcards(known_cards, known_filepath)
    logger.info("Moved card %s to known deck", card_id)