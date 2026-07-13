# Prism Wallpapers Studio

An advanced automation suite for creating luxury media backdrops and logo cards. Designed to construct perfectly balanced, visually high-end brand assets using custom visual math, dynamic perspective warping, and spatial gradient mesh engines.

![Nuvio Media Backdrop](https://github.com/bramst0ne/prism-wallpapers/blob/main/collections/networks/213-netflix/backdrops/t2_flat_4k.jpg)

---

## 🚀 One-Click Installation

The automated installers that will set up your Python environment, install dependencies, and create a Desktop shortcut for the GUI.

**Prerequisite:** Ensure [Python](https://www.python.org/downloads/) is installed on your system. *(On Windows, make sure to check "Add python.exe to PATH" during installation).*

#### 🪟 On Windows:
1. Click code in the upper right corner of the github page and download the zip.
2. Unzip the files and move them to you desired directory.
3. Double-click the `install_windows.bat` file.
4. The script will automatically build your virtual environment and install the required tools.
5. Once finished, launch the app using the new **Prism Wallpapers** shortcut on your Desktop.

#### 🍏 macOS & 🐧 Linux:
1. Click code in the upper right corner of the github page and download the zip.
2. Unzip the files and move them to you desired directory.
3. Open your terminal and navigate to the project folder.
4. Run the installer:
   ```bash
   chmod +x install_mac_linux.sh
   ./install_mac_linux.sh
5. Launch the app using the generated Desktop shortcut.

## 🔑 Setting Up Your API Keys
This project connects to TMDb, Fanart.tv, and Mdblist to pull high-quality logos and media assets. You can either enter your keys through the GUI or you can edit the env file.

If editing the env file:
1. Open the .env.example file in any text editor.
2. Paste your API keys after the = signs (you only need to configure the ones you will use, make all others empty):
    TMDB_API_KEY=your_actual_tmdb_key_here
    FANART_API_KEY=your_actual_fanart_key_here
    MDBLIST_API_KEY=your_actual_mdblist_key_here
3. Save the file as .env (remove the .example)

## 🖥️ Using the GUI Studio
The easiest way to generate backdrops is using the included visual interface.

Launch the program via your Desktop shortcut to access the Studio. From here, you can:

- Select Styles: Choose between Type 1 (Landscape) and Type 2 (Mixed Grid) in both 3D perspective and Flat layouts.

- Filter Data Sources: Pull dynamically from TMDb IDs, Curated TMDb Lists (like trending, popular, upcoming), or directly from custom MDBList URLs.

- Tweak Advanced Overrides: Adjust Depth of Field (DoF) blur, focus targets, perspective tilt, and layout gap spacing without touching the code.

- Add Text Overlays: Inject custom text into the layout, complete with custom system font selection, scaling, and alignment.

- Batch Resolutions: Generate 4K, 1080p, and 720p assets simultaneously.

## 🛠️ CLI Power-User Guide
For those building automated pipelines, you can bypass the GUI and invoke the scripts directly from your terminal.

### Project Structure
```
prism-wallpapers/
   ├── .env
   ├── install_windows.bat
   ├── install_mac_linux.sh
   ├── requirements.txt
   └── scripts/
       ├── gui_launcher.py
       ├── wallpaper_engine.py
       ├── logo_cards.py
       └── logo_pull.py
```
### 1. The Unified Wallpaper Engine (wallpaper_engine.py)
This script handles all backdrop generation (replacing the old individual layout scripts).

Usage Syntax:

`python scripts/wallpaper_engine.py --style <t1_3d|t1_flat|t2_3d|t2_flat> [options]`


Examples:
```
# Generate a 3D Mixed grid for Netflix (Movies Only) in 4K and 1080p
python scripts/wallpaper_engine.py --style t2_3d --id 213-movies --type network --res 4k 1080p

# Generate a Flat Landscape grid from a custom MDBList
python scripts/wallpaper_engine.py --style t1_flat --url "publicusername/top-rated-movies" --sort "score.desc"

# Generate a Curated Trending TV grid with a custom text overlay
python scripts/wallpaper_engine.py --style t2_3d --type curated --id trending-tv --text_overlay "Trending This Week" --text_align center
```

### 2. Logo Cards & Design Hotfixes (logo_cards.py)
This script places cropped, maximum-scale logos onto background cards. It features an integrated Design Hotfix Registry for precise positional nudges and advanced gradient generators.

- Background Configuration Options (--bg):

- Solid Color: --bg "0d0d11"

- Linear Gradient: --bg "linear:151515:282828:45"

- Radial Gradient: --bg "radial:24242c:0f0f13:0.35:0.35"

- Dual-Center Mesh: --bg "dual:2d1d2d:231a3a:0e0914:0.3:0.5:0.7:0.5"

Example:
```
python scripts/logo_cards.py --source both --bg "dual:2d1d2d:231a3a:0e0914:0.3:0.5:0.7:0.5"
```

### 3. Logo Extraction (logo_pull.py)
Downloads max-resolution logos from TMDB and processes them (including advanced color inversion and white-mask cutouts).

Example:
```
python scripts/logo_pull.py --id 213 49 --type network --max 1
```

## 🛡️ Content Safety & Blacklisting
All dynamic backdrop and card generation includes an integrated Adult Content Filter to ensure your server wallpapers remain professional. It actively blocks NSFW metadata at the API level.

To manually blacklist specific titles that slip through TMDB's filters, open wallpaper_engine.py and add the TMDB ID to the BLOCKED_IDS set at the top of the file.
