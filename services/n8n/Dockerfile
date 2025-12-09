FROM n8nio/n8n:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --no-cache-dir --upgrade pip setuptools

USER node
