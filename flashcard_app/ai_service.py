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

# NOTE: no "f" prefix here — this is a plain string template, filled in later
# via PROMPT_TEMPLATE.format(chunk=chunk). An f-string would try to evaluate
# {chunk} immediately when the module loads, before "chunk" even exists.
PROMPT_TEMPLATE = """
You are an expert educator and flashcard creator.

You will be given a piece of text extracted from a document. The text may be in ANY format, including:
- Plain paragraphs explaining concepts
- Tables or glossaries
- Bullet points
- Sentence fragments
- Already formatted question-answer pairs
- OCR output from scanned or handwritten documents

Your task is to identify every meaningful concept, fact, definition, process, relationship, or event that is worth remembering and convert them into high-quality flashcards.

Rules:

1. Read and understand the entire text before generating flashcards.
2. Generate one flashcard for each distinct concept or fact worth remembering.
3. Cover the content as completely as possible without creating redundant or overlapping flashcards.
4. If the text is a glossary or table (e.g. "Word - Meaning"), convert each row into a flashcard.
5. If the text already contains question-answer pairs, reuse and improve them if necessary.
6. If the text is prose, extract the key ideas and convert them into concise, self-contained questions.
7. Ignore page numbers, headers, footers, OCR artifacts, formatting noise, and incomplete fragments.
8. Questions should be clear, specific, and understandable without requiring the original text.
9. Answers should be concise while containing all essential information needed to answer the question.
10. Do not generate duplicate, trivial, or highly overlapping flashcards.
11. Do not invent information that is not explicitly supported by the provided text.
12. The number of flashcards should be determined solely by the amount of unique, meaningful information in the text. Generate as many high-quality flashcards as necessary to achieve complete conceptual coverage, but avoid unnecessary fragmentation of closely related ideas.

Return ONLY valid JSON in exactly this format:

{{
  "flashcards": [
    {{
      "question": "...",
      "answer": "..."
    }}
  ]
}}

Do not include markdown, explanations, or any text outside the JSON.

Text:
{chunk}
"""


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

    prompt = PROMPT_TEMPLATE.format(chunk=chunk)
    logger.info("Sending chunk to %s (%d chars)", AI_PROVIDER, len(chunk))

    if AI_PROVIDER == "groq":
        qa_pairs = await _call_groq(prompt)
    else:
        qa_pairs = await _call_ollama(prompt)

    logger.info("Final result: %d Q&A pairs", len(qa_pairs))
    return qa_pairs