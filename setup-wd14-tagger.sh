#!/bin/bash
# Setup script for wd14-tagger-server

if [ ! -d "services/wd14-tagger-server" ]; then
    echo "Cloning wd14-tagger-server repository..."
    git clone https://github.com/LlmKira/wd14-tagger-server.git services/wd14-tagger-server
    echo "Repository cloned successfully!"
else
    echo "Repository already exists at services/wd14-tagger-server"
fi

echo "You can now start the service with: docker compose up -d wd14-tagger"


