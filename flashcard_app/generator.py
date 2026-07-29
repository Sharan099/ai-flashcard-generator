import asyncio
import logging
import re

from flashcard_app.ai_service import generate_qa_pairs
from flashcard_app.models import Flashcard

logger = logging.getLogger(__name__)

QA_PATTERN = re.compile(r"Q\d+\.\s*(.+?)\n(.*?)(?=\nQ\d+\.|\Z)", re.DOTALL)


def try_parse_structured_qa(text: str) -> list[dict]:
    """Detect and extract pre-existing Q&A pairs (e.g., 'Q1. ... / answer') without needing the LLM."""
    matches = QA_PATTERN.findall(text)
    pairs = []
    for question, answer in matches:
        question = question.strip()
        answer = " ".join(answer.strip().split())  # collapse newlines/extra spaces into one line
        if question and answer:
            pairs.append({"question": question, "answer": answer})
    return pairs


def split_into_chunks(text: str, max_chunk_chars: int = 500) -> list[str]:
    """Split raw notes into chunks small enough for the LLM to process well."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]

    chunks = []
    current = ""
    for para in paragraphs:
        if len(current) + len(para) > max_chunk_chars and current:
            chunks.append(current)
            current = para
        else:
            current = f"{current}\n\n{para}" if current else para
    if current:
        chunks.append(current)

    return chunks


async def process_chunk(chunk: str, source: str = "manual") -> list[Flashcard]:
    """Turn one text chunk into Flashcard objects via the LLM."""
    logger.debug("Processing chunk (%d chars)", len(chunk))

    qa_pairs = await generate_qa_pairs(chunk)

    cards = [
        Flashcard(question=pair["question"], answer=pair["answer"],source=source)
        for pair in qa_pairs
        if "question" in pair and "answer" in pair
    ]
    return cards


async def generate_flashcards(text: str, source: str = "manual") -> list[Flashcard]:
    """Generate flashcards — reuse existing Q&A structure if detected, else use the LLM."""

    structured_pairs = try_parse_structured_qa(text)

    if len(structured_pairs) >= 3:
        logger.info("Detected %d pre-structured Q&A pairs — skipping LLM entirely", len(structured_pairs))
        return [Flashcard(question=p["question"], answer=p["answer"], source=source) for p in structured_pairs]

    logger.info("No clear Q&A structure found — falling back to LLM generation")
    chunks = split_into_chunks(text)
    if not chunks:
        logger.warning("No valid text chunks found in input")
        return []

    all_results = []
    for chunk in chunks:
        cards = await process_chunk(chunk,source=source)
        all_results.append(cards)

    all_cards = [card for chunk_cards in all_results for card in chunk_cards]
    logger.info("Total flashcards generated: %d", len(all_cards))
    return all_cards