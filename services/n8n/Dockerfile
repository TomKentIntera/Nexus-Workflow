FROM n8nio/n8n:latest

USER root

RUN apk add --no-cache python3 py3-pip python3-dev git \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --no-cache-dir --break-system-packages --upgrade pip setuptools

COPY scripts /mnt/scripts

RUN python -m pip install --no-cache-dir --break-system-packages -r /mnt/scripts/requirements.txt \
    && chmod +x /mnt/scripts/images/generate.py \
    && chown -R node:node /mnt/scripts

USER node
