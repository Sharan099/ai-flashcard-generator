"""Calls either a local LLM (Ollama) or a cloud LLM (Groq) to generate flashcard Q&A pairs."""

import json
import logging
import os
import re

import httpx
from dotenv import load_dotenv

load_dotenv()  # reads .env file into environment variables, if present

logger = logging.getLogger(__name__)

AI_PROVIDER = os.getenv("AI_PROVIDER", "ollama")  # "ollama" or "groq"

# --- Ollama (local) settings ---
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3.2:3b-instruct-q4_K_M"

# --- Groq (cloud) settings ---
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"
GROQ_API_KEY = os.getenv("GROQ_API_KEY")

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
- You MUST produce EXACTLY {target_count} flashcards. Not more, not fewer.

Respond with a JSON object of exactly this shape:
{{"flashcards": [{{"question": "...", "answer": "..."}}]}}

Text:
{chunk}
"""


def calculate_target_count(chunk: str) -> int:
    """Estimate a reasonable number of flashcards based on content length."""
    word_count = len(chunk.split())
    target = word_count // 25
    return max(2, min(target, 8))


def _extract_qa_with_regex(raw_text: str) -> list[dict]:
    """Fallback: pull question/answer pairs out with regex if JSON parsing fails."""
    pattern = r'"question"\s*:\s*"(.*?)"\s*,?\s*"answer"\s*:\s*"(.*?)"'
    matches = re.findall(pattern, raw_text, re.DOTALL)
    return [{"question": q, "answer": a} for q, a in matches]


def _parse_response(raw_text: str) -> list[dict]:
    """Shared parsing logic for both providers' text output."""
    raw_text = raw_text.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    try:
        parsed = json.loads(raw_text)
        if isinstance(parsed, dict):
            return parsed.get("flashcards", [])
        if isinstance(parsed, list):
            return parsed
        return []
    except json.JSONDecodeError:
        logger.warning("JSON parse failed, trying regex fallback")
        qa_pairs = _extract_qa_with_regex(raw_text)
        if not qa_pairs:
            logger.error("Regex fallback also failed. Raw text: %s", raw_text[:200])
        return qa_pairs


async def _call_ollama(prompt: str) -> list[dict]:
    """Call the local Ollama server."""
    async with httpx.AsyncClient(timeout=180.0) as client:
        response = await client.post(
            OLLAMA_URL,
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False,
                "format": RESPONSE_SCHEMA,
                "temperature": 0.3,
            },
        )
        response.raise_for_status()
        result = response.json()
    return _parse_response(result["response"])


async def _call_groq(prompt: str) -> list[dict]:
    """Call Groq's cloud API (OpenAI-compatible format)."""
    if not GROQ_API_KEY:
        logger.error("GROQ_API_KEY is not set — cannot call Groq")
        return []

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            GROQ_URL,
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            json={
                "model": GROQ_MODEL,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.3,
                "response_format": {"type": "json_object"},
            },
        )
        response.raise_for_status()
        result = response.json()

    raw_text = result["choices"][0]["message"]["content"]
    return _parse_response(raw_text)


async def generate_qa_pairs(chunk: str) -> list[dict]:
    """Generate flashcards from one chunk, using whichever provider is configured."""
    target_count = calculate_target_count(chunk)
    prompt = PROMPT_TEMPLATE.format(chunk=chunk, target_count=target_count)

    logger.info("Sending chunk to %s (%d chars, target %d pairs)", AI_PROVIDER, len(chunk), target_count)

    if AI_PROVIDER == "groq":
        qa_pairs = await _call_groq(prompt)
    else:
        qa_pairs = await _call_ollama(prompt)

    if len(qa_pairs) < target_count:
        logger.warning("Got %d pairs, wanted %d — retrying once", len(qa_pairs), target_count)
        if AI_PROVIDER == "groq":
            qa_pairs = await _call_groq(prompt)
        else:
            qa_pairs = await _call_ollama(prompt)

    logger.info("Final result: %d Q&A pairs (target was %d)", len(qa_pairs), target_count)
    return qa_pairs