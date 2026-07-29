import json
import logging
import re

import httpx

logger = logging.getLogger(__name__)

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "llama3.2:3b-instruct-q4_K_M"

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "flashcards": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "question": {"type": "string"},
                    "answer": {"type": "string"},
                },
                "required": ["question", "answer"],
            },
        }
    },
    "required": ["flashcards"],
}

PROMPT_TEMPLATE = """You will be given a piece of text extracted from a document. The text could be in ANY format:
- Plain paragraphs explaining concepts
- A table or list (e.g. word — meaning — example)
- Bullet points or sentence fragments
- Already-formatted questions and answers
- Messy OCR output from a scanned or handwritten page

Your job: identify the individual facts, terms, or concepts in this text, and produce clear
question/answer flashcard pairs from them — regardless of how the original text was structured.

Rules:
- If the text is a glossary/table (e.g. "word - meaning"), turn each row into a question like
  "What does <word> mean?" with the meaning as the answer.
- If the text is already Q&A, reuse it directly.
- If the text is prose or narrative, extract the key facts, characters, or events and phrase them as questions.
- Ignore page numbers, headers, or fragments that are not real content.
- You MUST produce EXACTLY {target_count} flashcards. Not more, not fewer. If the text seems
  thin, still find {target_count} distinct angles (characters, events, definitions, causes, effects).

Respond with ONLY a JSON array of exactly {target_count} objects, nothing else, in this shape:
[{{"question": "...", "answer": "..."}}]

Text:
{chunk}
"""

def calculate_target_count(chunk: str) -> int:
    """Estimate a reasonable number of flashcards based on how much real content is in the chunk."""
    word_count = len(chunk.split())
    target = word_count // 25   # roughly one flashcard per 25 words of content
    return max(2, min(target, 8))   # never fewer than 2, never more than 8 per chunk

def _extract_qa_with_regex(raw_text: str) -> list[dict]:
    """Fallback: pull question/answer pairs out with regex if JSON parsing fails."""
    pattern = r'"question"\s*:\s*"(.*?)"\s*,?\s*"answer"\s*:\s*"(.*?)"'
    matches = re.findall(pattern, raw_text, re.DOTALL)
    return [{"question": q, "answer": a} for q, a in matches]

async def generate_qa_pairs(chunk: str) -> list[dict]:
    """Send one text chunk (any format) to the local LLM and get back Q&A pairs."""
    target_count = calculate_target_count(chunk)
    qa_pairs = await _call_llm(chunk, target_count)

    if len(qa_pairs) < target_count:
        logger.warning(
            "Got %d pairs, wanted %d — retrying once", len(qa_pairs), target_count
        )
        qa_pairs = await _call_llm(chunk, target_count)

    logger.info("Final result: %d Q&A pairs (target was %d)", len(qa_pairs), target_count)
    return qa_pairs


async def _call_llm(chunk: str, target_count: int) -> list[dict]:
    """One actual call to Ollama — separated out so we can retry cleanly."""
    prompt = PROMPT_TEMPLATE.format(chunk=chunk, target_count=target_count)

    logger.info("Sending chunk to LLM (%d chars, target %d pairs)", len(chunk), target_count)

    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": False,
                "format": RESPONSE_SCHEMA,
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        result = response.json()

    raw_text = result["response"].strip()
    raw_text = raw_text.removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    

    try:
        parsed = json.loads(raw_text)
        return parsed.get("flashcards", [])
    except json.JSONDecodeError:
        logger.warning("JSON parse failed, trying regex fallback")
        qa_pairs = _extract_qa_with_regex(raw_text)
        if not qa_pairs:
            logger.error("Regex fallback also failed. Raw text: %s", raw_text[:200])
        return qa_pairs