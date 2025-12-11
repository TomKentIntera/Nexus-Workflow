#!/bin/bash
# Don't exit on error for Docker restart step (Docker Desktop doesn't use systemd)
set -e

echo "Installing NVIDIA Container Toolkit..."

# Add GPG key
echo "Step 1: Adding GPG key..."
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

# Add repository
echo "Step 2: Adding repository..."
curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

# Update package list
echo "Step 3: Updating package list..."
sudo apt-get update

# Install toolkit
echo "Step 4: Installing NVIDIA Container Toolkit..."
sudo apt-get install -y nvidia-container-toolkit

# Configure Docker
echo "Step 5: Configuring Docker runtime..."
sudo nvidia-ctk runtime configure --runtime=docker

# Restart Docker
echo "Step 6: Restarting Docker..."
# Docker Desktop on WSL2 doesn't use systemd - it runs as a Windows service
# The nvidia-ctk configure command should have updated the Docker daemon config
echo "⚠️  Docker Desktop runs as a Windows service, not a Linux service."
echo "   Please restart Docker Desktop manually:"
echo ""
echo "   Option 1: From system tray"
echo "   - Right-click Docker Desktop icon in Windows system tray"
echo "   - Select 'Restart' or 'Quit Docker Desktop' then start it again"
echo ""
echo "   Option 2: From Docker Desktop"
echo "   - Open Docker Desktop"
echo "   - Click the Settings (gear) icon"
echo "   - Click 'Restart' button"
echo ""
echo "   After restarting, the NVIDIA runtime will be available."

echo ""
echo "✅ Installation complete!"
echo ""
echo "⚠️  IMPORTANT: Please restart Docker Desktop now before verifying!"
echo "   (See instructions above)"
echo ""
read -p "Press Enter after you've restarted Docker Desktop to verify installation..."
echo ""
echo "Verifying installation..."
if docker run --rm --gpus all nvidia/cuda:12.1.0-base-ubuntu22.04 nvidia-smi; then
    echo ""
    echo "🎉 NVIDIA Container Toolkit is installed and working!"
else
    echo ""
    echo "❌ Verification failed. Make sure:"
    echo "   1. Docker Desktop has been restarted"
    echo "   2. Your GPU drivers are up to date"
    echo "   3. WSL2 has GPU access (run 'nvidia-smi' in WSL to verify)"
fi

