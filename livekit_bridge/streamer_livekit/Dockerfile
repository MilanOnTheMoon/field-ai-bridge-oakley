# Lean LiveKit webcam streamer.
FROM python:3.12-slim

# - libgl1        : opencv-python wheel needs libGL.so.1
# - libglib2.0-0  : opencv-python wheel needs libgthread-2.0.so.0
RUN apt-get update && apt-get install -y --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv: single static binary, faster than pip and reads the existing uv.lock
# for reproducible installs.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /usr/local/bin/

WORKDIR /app

# Install Python deps first so editing source doesn't bust the dep layer.
# --no-install-project skips installing the streamer-livekit package itself
# (we run main.py directly, no package import needed).
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Source last so edits are a fast rebuild.
COPY main.py ./

# Use the venv's python so deps resolve without `uv run`.
ENV PATH="/app/.venv/bin:$PATH"

ENTRYPOINT ["python", "-u", "main.py"]
CMD []
