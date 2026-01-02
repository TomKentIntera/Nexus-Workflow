FROM python:3.11-slim
WORKDIR /usr/src/app

# Install system dependencies including build tools
RUN apt-get update && apt-get install -y \
    libgl1 \
    libglib2.0-0 \
    build-essential \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency files first for better caching
COPY pyproject.toml pdm.lock ./

# Install PDM with specific version for stability
RUN pip install --no-cache-dir "pdm>=2.0.0"

# Configure PDM to use the system Python (not create a venv)
ENV PDM_USE_VENV=false

# Disable HTTP cache to avoid SQLite lock issues during concurrent installs
ENV UNEARTH_NO_CACHE=1
ENV PDM_NO_CACHE=1

# Install dependencies sequentially to avoid cache lock issues
RUN pdm install --no-self --no-editable --no-isolation || \
    (echo "First attempt failed, retrying..." && \
     sleep 5 && \
     pdm install --no-self --no-editable --no-isolation) || \
    (echo "Second attempt failed, trying with pip directly..." && \
     pip install --no-cache-dir \
     onnxruntime>=1.17.0 \
     pydantic-settings>=2.1.0 \
     loguru>=0.7.2 \
     aiohttp>=3.9.1 \
     rich>=13.7.0 \
     Pillow>=10.1.0 \
     opencv-python>=4.8.1.78 \
     pandas>=2.0.3 \
     nest-asyncio>=1.5.8 \
     httpx>=0.25.2 \
     robust-downloader>=0.0.2 \
     fastapi>=0.105.0 \
     uvicorn>=0.24.0.post1 \
     python-multipart>=0.0.6 \
     aiofiles>=23.2.1 \
     python-dotenv>=1.0.0 \
     "numpy>=1.24.4,<2.0.0")

# Copy the rest of the application
COPY . .

# Setup environment
RUN cp .env.exp .env
RUN sed -i 's|SERVER_HOST=127.0.0.1|SERVER_HOST=0.0.0.0|' .env

CMD ["pdm", "run", "python3", "main.py"]