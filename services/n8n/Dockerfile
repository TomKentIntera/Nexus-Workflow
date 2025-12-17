FROM n8nio/n8n:latest

USER root

RUN apk add --no-cache python3 py3-pip python3-dev git \
    && ln -sf /usr/bin/python3 /usr/local/bin/python \
    && python -m pip install --no-cache-dir --break-system-packages --upgrade pip setuptools

COPY scripts /mnt/scripts

RUN python -m pip install --no-cache-dir --break-system-packages -r /mnt/scripts/requirements.txt \
    && chmod +x /mnt/scripts/images/generate.py \
    && chmod +x /mnt/scripts/images/generate_cli.py \
    && chown -R node:node /mnt/scripts

# Create Python virtual environment for n8n task runner
# n8n looks for the venv in the user's home directory
RUN mkdir -p /home/node/.n8n \
    && python3 -m venv /home/node/.n8n/.venv \
    && /home/node/.n8n/.venv/bin/pip install --upgrade pip setuptools \
    && /home/node/.n8n/.venv/bin/pip install requests \
    && chown -R node:node /home/node/.n8n

USER node
