FROM python:3.13-slim

# Install Tesseract OCR (a system package, not a Python package)
RUN apt-get update && apt-get install -y tesseract-ocr && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install uv itself inside the container
RUN pip install uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY . .

# Render sets $PORT dynamically — we must listen on whatever it assigns
CMD ["sh", "-c", "uv run uvicorn flashcard_app.api:app --host 0.0.0.0 --port $PORT"]