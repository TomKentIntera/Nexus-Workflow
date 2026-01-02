# Setup script for wd14-tagger-server (PowerShell)

if (-not (Test-Path "services\wd14-tagger-server")) {
    Write-Host "Cloning wd14-tagger-server repository..."
    git clone https://github.com/LlmKira/wd14-tagger-server.git services\wd14-tagger-server
    Write-Host "Repository cloned successfully!"
} else {
    Write-Host "Repository already exists at services\wd14-tagger-server"
}

Write-Host "You can now start the service with: docker compose up -d wd14-tagger"


