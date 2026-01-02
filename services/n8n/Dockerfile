FROM n8nio/n8n:latest

USER root

# Check if Python is already available, if not try to install it
RUN if command -v python3 > /dev/null || command -v python > /dev/null; then \
        echo "Python already available"; \
    elif command -v apk > /dev/null; then \
        apk add --no-cache python3 py3-pip python3-dev git; \
    elif command -v apt-get > /dev/null; then \
        apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-dev git && apt-get clean && rm -rf /var/lib/apt/lists/*; \
    else \
        echo "Python not available and no package manager found. Skipping Python installation."; \
    fi

# Create symlink if Python3 exists but python doesn't
RUN (command -v python > /dev/null || (command -v python3 > /dev/null && ln -sf /usr/bin/python3 /usr/local/bin/python)) || true

# Install pip packages if Python is available
RUN if command -v python > /dev/null || command -v python3 > /dev/null; then \
        (python -m pip install --no-cache-dir --break-system-packages --upgrade pip setuptools || python3 -m pip install --no-cache-dir --break-system-packages --upgrade pip setuptools) || true; \
    fi

COPY scripts /mnt/scripts

# Install script dependencies if Python is available
RUN if command -v python > /dev/null || command -v python3 > /dev/null; then \
        (python -m pip install --no-cache-dir --break-system-packages -r /mnt/scripts/requirements.txt || python3 -m pip install --no-cache-dir --break-system-packages -r /mnt/scripts/requirements.txt) || true; \
    fi \
    && chmod +x /mnt/scripts/images/generate.py \
    && chmod +x /mnt/scripts/images/generate_cli.py \
    && chmod +x /mnt/scripts/cypress/run_tests.py \
    && chown -R node:node /mnt/scripts

# Install Cypress (as node user to avoid permission issues)
USER node
RUN npm install -g cypress@latest || echo "Cypress installation failed - may need to be installed per-project"
USER root

# Create Python virtual environment for n8n task runner (only if Python is available)
# n8n looks for the venv in the user's home directory
RUN if command -v python3 > /dev/null || command -v python > /dev/null; then \
        mkdir -p /home/node/.n8n \
        && (python3 -m venv /home/node/.n8n/.venv || python -m venv /home/node/.n8n/.venv) \
        && /home/node/.n8n/.venv/bin/pip install --upgrade pip setuptools \
        && /home/node/.n8n/.venv/bin/pip install requests \
        && chown -R node:node /home/node/.n8n; \
    else \
        echo "Skipping venv creation - Python not available"; \
    fi

USER node
