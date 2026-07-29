"""CLI entry point for the AI Flashcard Generator."""

import asyncio
import logging

from flashcard_app.generator import generate_flashcards
from flashcard_app.storage import load_flashcards, save_flashcards

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


async def run() -> None:
    """Main app flow: get notes, generate flashcards, save, display."""
    print("=== AI Flashcard Generator ===")
    print("Paste your notes (as one block of text), then press Enter:\n")

    notes = input("> ")

    if not notes.strip():
        logger.warning("No input provided. Exiting.")
        return

    new_cards = await generate_flashcards(notes)

    if not new_cards:
        print("No flashcards could be generated from that text. Try longer sentences.")
        return

    existing_cards = load_flashcards()
    all_cards = existing_cards + new_cards
    save_flashcards(all_cards)

    print(f"\nGenerated {len(new_cards)} new flashcard(s):\n")
    for i, card in enumerate(new_cards, start=1):
        print(f"{i}. Q: {card.question}")
        print(f"   A: {card.answer}\n")

    print(f"Total flashcards saved: {len(all_cards)}")


def main() -> None:
    """Synchronous entry point (required since some tools expect a normal function)."""
    asyncio.run(run())


if __name__ == "__main__":
    main()