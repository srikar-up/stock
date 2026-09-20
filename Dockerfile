FROM python:3.11-slim

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=7860

# Install minimal OS dependencies for C++ compilation and fonts
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set up non-root user (UID 1000 standard for Hugging Face Spaces)
RUN useradd -m -u 1000 user
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH

WORKDIR $HOME/app

# Install Python requirements
COPY --chown=user requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt
RUN pip install --no-cache-dir --user cactus-needle || true

# Copy application files
COPY --chown=user . $HOME/app

# Switch to non-root user
USER user

# Expose standard Hugging Face Spaces port
EXPOSE 7860

# Launch FastAPI web application and background listener
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "7860"]
