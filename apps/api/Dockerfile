FROM python:3.12-slim

WORKDIR /srv/api

# Tesseract OCR engine (Phase 2): system binary + English data. Baked into the
# image so extraction never downloads anything at container start.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# torch MUST come from the CPU index first (Phase 3/5): a plain pip install
# would pull the multi-GB CUDA build. The unpinned `torch` line in
# requirements.txt is then already satisfied and skipped.
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt \
    && python -m spacy download en_core_web_sm

# Bake the MiniLM weights (Phase 3): correlation must work with the venue
# network dead. Guard the no_proxy env: some sandboxes set a bracketed-IPv6
# no_proxy that crashes httpx inside huggingface_hub (InvalidURL).
# The deepfake model is deliberately NOT baked (image weight); media.py
# lazy-loads it at runtime and degrades gracefully without it.
RUN env -u no_proxy -u NO_PROXY \
    python -c "from sentence_transformers import SentenceTransformer; \
SentenceTransformer('all-MiniLM-L6-v2')"

COPY app ./app

# The "Operation Ledger" demo case (1.2 MB, deterministic): baked in so the
# seeder runs inside the container with zero host dependencies.
COPY seeds ./seeds

# Runtime is offline-safe: all baked models are on disk, so forbid any
# hub/network fetch at request time (fast, deterministic failures).
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    DATA_DIR=/srv/api/data \
    DB_PATH=/srv/api/data/forensics.db
VOLUME /srv/api/data

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
