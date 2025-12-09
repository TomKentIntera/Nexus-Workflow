FROM n8nio/n8n:latest

USER root

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git \
    && rm -rf /var/lib/apt/lists/* \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --no-cache-dir --upgrade pip setuptools

COPY scripts /mnt/scripts

RUN python -m pip install --no-cache-dir -r /mnt/scripts/requirements.txt \
    && chmod +x /mnt/scripts/images/generate.py \
    && chown -R node:node /mnt/scripts

USER node
