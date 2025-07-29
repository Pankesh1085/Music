#!/bin/bash

# Music Downloader - Full Auto Installer
# Usage: sudo ./auto-install.sh

set -euo pipefail

# Configuration
APP_NAME="music-downloader"
APP_USER="spotdluser"
APP_DIR="/opt/$APP_NAME"
VENV_DIR="$APP_DIR/venv"
DOWNLOAD_DIR="/media/Music"
SERVICE_FILE="/etc/systemd/system/$APP_NAME.service"
GITHUB_REPO="https://github.com/Pankesh1085/Music.git"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Spotify Downloader Auto Installer ===${NC}"

# Check root
[ "$(id -u)" -ne 0 ] && { echo -e "${RED}Run as root: sudo ./auto-install.sh${NC}"; exit 1; }

# Install system dependencies
echo -e "${GREEN}[1/6] Installing system packages...${NC}"
apt update -qq
apt install -y git ffmpeg python3 python3-pip python3-venv

# Create system user
echo -e "${GREEN}[2/6] Configuring $APP_USER user...${NC}"
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
fi

# Clone repository
echo -e "${GREEN}[3/6] Downloading application...${NC}"
[ -d "$APP_DIR" ] || mkdir -p "$APP_DIR"
chown "$APP_USER:$APP_USER" "$APP_DIR"
sudo -u "$APP_USER" git clone "$GITHUB_REPO" "$APP_DIR" 2>/dev/null || {
    cd "$APP_DIR"
    sudo -u "$APP_USER" git pull
}

# Python environment
echo -e "${GREEN}[4/6] Setting up Python environment...${NC}"
sudo -u "$APP_USER" python3 -m venv "$VENV_DIR"
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$VENV_DIR/bin/pip" install -r "$APP_DIR/requirements.txt"

# Download directory
echo -e "${GREEN}[5/6] Configuring download directory...${NC}"
mkdir -p "$DOWNLOAD_DIR"
chown "$APP_USER:$APP_USER" "$DOWNLOAD_DIR"
chmod 775 "$DOWNLOAD_DIR"

# Systemd service
echo -e "${GREEN}[6/6] Creating system service...${NC}"
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=Spotify Music Downloader
After=network.target

[Service]
User=$APP_USER
WorkingDirectory=$APP_DIR
ExecStart=$VENV_DIR/bin/python $APP_DIR/app.py
Restart=always
Environment="PYTHONUNBUFFERED=1"

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable --now "$APP_NAME"

# Completion
echo -e "${GREEN}\n✔ Installation Complete!${NC}"
echo -e "\n${YELLOW}Access the web interface:${NC}"
echo "http://$(hostname -I | cut -d' ' -f1):5000"
echo -e "\n${YELLOW}Service commands:${NC}"
echo "sudo systemctl stop $APP_NAME"
echo "sudo systemctl start $APP_NAME"
echo "sudo journalctl -u $APP_NAME -f"
