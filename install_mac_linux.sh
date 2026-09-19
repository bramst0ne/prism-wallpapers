#!/bin/bash
echo "==================================================="
echo "     Prism Wallpapers - One-Click Installer"
echo "==================================================="

# 1. Check for Python
if ! command -v python3 &> /dev/null; then
    echo "[ERROR] Python 3 is not installed."
    exit 1
fi

echo "[1/4] Creating isolated Python environment..."
python3 -m venv venv

echo "[2/4] Installing required libraries..."
source venv/bin/activate
pip install --upgrade pip >/dev/null 2>&1
pip install -r requirements.txt

echo "[3/4] Preparing configuration files..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  - Created default .env file."
fi

echo "[4/4] Creating Desktop Shortcut..."
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS Shortcut
    SHORTCUT="$HOME/Desktop/Launch Prism.command"
    echo '#!/bin/bash' > "$SHORTCUT"
    echo "cd \"$(pwd)\"" >> "$SHORTCUT"
    echo "source venv/bin/activate" >> "$SHORTCUT"
    echo "python scripts/gui_launcher.py" >> "$SHORTCUT"
    chmod +x "$SHORTCUT"
else
    # Linux Desktop Entry
    SHORTCUT="$HOME/Desktop/PrismWallpapers.desktop"
    echo "[Desktop Entry]" > "$SHORTCUT"
    echo "Type=Application" >> "$SHORTCUT"
    echo "Name=Prism Wallpapers" >> "$SHORTCUT"
    echo "Exec=bash -c 'cd \"$(pwd)\" && source venv/bin/activate && python scripts/gui_launcher.py'" >> "$SHORTCUT"
    echo "Terminal=false" >> "$SHORTCUT"
    chmod +x "$SHORTCUT"
fi

echo ""
echo "SUCCESS! You can now launch the app using the shortcut on your Desktop."