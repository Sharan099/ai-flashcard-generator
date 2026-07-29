import logging

import fitz  # PyMuPDF
import pytesseract
from PIL import Image
import io

logger = logging.getLogger(__name__)

MIN_TEXT_LENGTH_THRESHOLD = 100  # if a page has less real text than this, treat it as scanned


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract text from every page of a PDF, using OCR for scanned pages."""
    doc = fitz.open(pdf_path)
    full_text = []
    page_count = len(doc) 
    for page_num, page in enumerate(doc, start=1):
        native_text = page.get_text().strip()

        if len(native_text) >= MIN_TEXT_LENGTH_THRESHOLD:
            logger.info("Page %d: using native text (%d chars)", page_num, len(native_text))
            full_text.append(native_text)
        else:
            logger.info("Page %d: no native text found, running OCR", page_num)
            pix = page.get_pixmap(dpi=300)
            img_bytes = pix.tobytes("png")
            image = Image.open(io.BytesIO(img_bytes))
            ocr_text = pytesseract.image_to_string(image)
            full_text.append(ocr_text.strip())

    doc.close()
    combined = "\n\n".join(full_text)
    logger.info("Extracted %d total characters from %d page(s)", len(combined), page_count)
    return combined



if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    pdf_file = "H:/git-lab/ai-flashcard-generator/notes/Random_Study_Notes.pdf"
    text = extract_text_from_pdf(pdf_file)
    print("\n--- EXTRACTED TEXT ---\n")
    print(text)