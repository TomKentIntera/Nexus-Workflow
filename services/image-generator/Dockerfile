FROM nvidia/cuda:12.1.0-cudnn8-runtime-ubuntu22.04

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DEBIAN_FRONTEND=noninteractive

WORKDIR /app

# Install Python 3.11 and system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    python3.11 \
    python3.11-dev \
    python3-pip \
    build-essential \
    git \
    libssl-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/* \
    && rm -f /usr/bin/python /usr/bin/python3 \
    && ln -s /usr/bin/python3.11 /usr/bin/python \
    && ln -s /usr/bin/python3.11 /usr/bin/python3

# Install NumPy first (pin to <2.0 for PyTorch compatibility)
RUN pip install --no-cache-dir "numpy<2.0"

# Install PyTorch with CUDA support
RUN pip install --no-cache-dir \
    torch==2.2.2 \
    torchvision==0.17.2 \
    torchaudio==2.2.2 \
    --index-url https://download.pytorch.org/whl/cu121

# Install huggingface_hub first (compatible version)
RUN pip install --no-cache-dir "huggingface_hub>=0.20.0,<0.26.0"

# Install ML dependencies
RUN pip install --no-cache-dir \
    "diffusers==0.21.4" \
    "transformers==4.35.0" \
    "accelerate==0.24.1" \
    "pillow==10.1.0" \
    "safetensors==0.4.1" \
    "requests>=2.31.0" \
    "cryptography>=41.0.0"

# Install FastAPI and uvicorn for HTTP API
RUN pip install --no-cache-dir \
    fastapi==0.115.4 \
    uvicorn[standard]==0.32.0

# Install MinIO client for object storage
RUN pip install --no-cache-dir \
    minio==7.2.3

# Install database dependencies
COPY services/image-generator/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy the generator module, database module, and worker
COPY services/image-generator/generator.py /app/generator.py
COPY services/image-generator/db.py /app/db.py
COPY services/image-generator/worker.py /app/worker.py

# Copy the logo file
COPY patreon_logo.png /app/patreon_logo.png

# Create output directory
RUN mkdir -p /app/generated-images

# Run the worker
CMD ["python", "worker.py"]

