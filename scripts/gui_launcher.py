import tkinter as tk
from tkinter import ttk, messagebox
import subprocess
import threading
import platform
import sys
import os
import requests
from dotenv import load_dotenv, set_key
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageTk


class WallpaperGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Wallpaper Generator Studio")
        self.root.geometry("800x600")

        # --- SCROLLABLE FRAME SETUP ---
        main_container = ttk.Frame(root)
        main_container.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(main_container, highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(main_container, orient="vertical", command=self.canvas.yview)

        self.scrollable_frame = ttk.Frame(self.canvas)
        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.frame_id = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")

        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfig(self.frame_id, width=e.width)
        )

        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

        # FIX: Bind mousewheel for all platforms correctly
        self.canvas.bind_all("<MouseWheel>", self._on_mousewheel)   # Windows & macOS
        self.canvas.bind_all("<Button-4>", self._on_mousewheel)     # Linux scroll up
        self.canvas.bind_all("<Button-5>", self._on_mousewheel)     # Linux scroll down

        self.scrollable_frame.columnconfigure(0, weight=1)

        # --- Style Selection ---
        frame_style = ttk.LabelFrame(self.scrollable_frame, text="1. Select Style", padding=10)
        frame_style.grid(row=0, column=0, sticky="ew", padx=10, pady=5)

        self.style_var = tk.StringVar(value="t1_3d")
        styles = [
            ("Type 1 (Landscape 3D)", "t1_3d"),
            ("Type 1 (Landscape Flat)", "t1_flat"),
            ("Type 2 (Mixed 3D)", "t2_3d"),
            ("Type 2 (Mixed Flat)", "t2_flat"),
            ("Type 3 (Landscape 3D w/ logo)", "t3_3d"),
            ("Type 3 (Landscape flat w/ logo)", "t3_flat")
        ]
        for text, val in styles:
            ttk.Radiobutton(frame_style, text=text, value=val, variable=self.style_var).pack(anchor="w")

        # --- Input Source ---
        frame_input = ttk.LabelFrame(self.scrollable_frame, text="2. Data Source", padding=10)
        frame_input.grid(row=1, column=0, sticky="ew", padx=10, pady=5)

        self.mode_var = tk.StringVar(value="mdblist")
        ttk.Radiobutton(frame_input, text="MDBList URLs (space separated)", value="mdblist",
                        variable=self.mode_var, command=self.toggle_mode).pack(anchor="w")
        ttk.Radiobutton(frame_input, text="TMDb IDs (requires Type)", value="tmdb",
                        variable=self.mode_var, command=self.toggle_mode).pack(anchor="w")
        ttk.Radiobutton(frame_input, text="TMDb Curated (no ID needed)", value="curated",
                        variable=self.mode_var, command=self.toggle_mode).pack(anchor="w")

        self.input_entry = ttk.Entry(frame_input, width=25)
        self.input_entry.pack(fill="x", pady=5)

        # TMDb ID mode — type selector
        self.type_frame = ttk.Frame(frame_input)
        ttk.Label(self.type_frame, text="TMDb Type:").pack(side="left")
        self.type_var = tk.StringVar(value="network")
        self.type_combo = ttk.Combobox(
            self.type_frame, textvariable=self.type_var,
            values=["network", "company", "provider", "genre", "person"],
            state="readonly", width=120
        )
        self.type_combo.pack(side="left", padx=5)

        # Curated mode — keyword selector (no ID entry needed)
        self.curated_frame = ttk.Frame(frame_input)
        ttk.Label(self.curated_frame, text="Keyword:").pack(side="left")
        self.curated_var = tk.StringVar(value="trending")
        curated_options = [
            "trending", "trending-day", "trending-week",
            "trending-movies", "trending-tv",
            "now_playing", "upcoming",
            "airing_today", "on_the_air",
            "popular", "popular-movies", "popular-tv",
            "top_rated", "top_rated-movies", "top_rated-tv",
        ]
        self.curated_combo = ttk.Combobox(
            self.curated_frame, textvariable=self.curated_var,
            values=curated_options, state="readonly", width=22
        )
        self.curated_combo.pack(side="left", padx=5)

        # MDBList mode — sort selector
        self.sort_frame = ttk.Frame(frame_input)
        ttk.Label(self.sort_frame, text="MDBList Sort:").pack(side="left")
        self.sort_var = tk.StringVar(value="score.desc")
        mdblist_sort_options = [
            "score.desc", "score_average.desc", "rank.desc",
            "imdbrating.desc", "imdbvotes.desc", "imdbpopular.desc",
            "tmdbpopular.desc", "rogerebert.desc", "rtomatoes.desc", "rtaudience.desc",
            "metacritic.desc", "myanimelist.desc", "letterrating.desc", "lettervotes.desc",
            "released.desc", "releasedigital.desc", "last_air_date.desc", "added.desc",
            "budget.desc", "revenue.desc", "runtime.desc",
            "title.asc", "sort_title.asc", "random"
        ]
        self.sort_combo = ttk.Combobox(
            self.sort_frame, textvariable=self.sort_var,
            values=mdblist_sort_options, state="normal", width=25
        )
        self.sort_combo.pack(side="left", padx=5)

        self.toggle_mode()

        # --- Advanced Customization (Tabs) ---
        frame_config = ttk.LabelFrame(
            self.scrollable_frame,
            text="3. Advanced Overrides & Filters (Leave blank for defaults)",
            padding=10
        )
        frame_config.grid(row=2, column=0, sticky="ew", padx=10, pady=5)

        self.notebook = ttk.Notebook(frame_config)
        self.notebook.pack(fill="x", expand=True)

        # FIX: Each item is a tuple: (label_text, cli_flag) or (label_text, cli_flag, [options])
        self.param_schema = {
            "TMDb Filters": [
                ("Sort By", "--tmdb_sort", [
                    "popularity.desc", "popularity.asc",
                    "vote_average.desc", "vote_average.asc",
                    "vote_count.desc", "vote_count.asc",
                    "primary_release_date.desc", "primary_release_date.asc",
                    "first_air_date.desc", "first_air_date.asc",
                    "revenue.desc", "revenue.asc",
                    "title.asc", "title.desc",
                    "name.asc", "name.desc"
                ]),
                ("Release Year", "--tmdb_year"),
                ("Language (e.g. en-US)", "--tmdb_lang", ["en-US", "ja-JP", "ko-KR", "es-ES", "fr-FR"]),
                ("Min Vote Avg (0-10)", "--tmdb_vote_min"),
                ("Min Vote Count", "--tmdb_vote_count"),
            ],
            "MDBList Filters": [
                ("Media Type", "--mdblist_mediatype", ["all", "movie", "show"]),
            ],
            "Layout & Scale": [
                ("Fetch Count", "--fetch_count"),
                ("Landscape Width", "--landscape_w"),
                ("Portrait Width", "--portrait_w"),
                ("Tile Gap", "--gap"),
                ("Card Radius", "--card_radius"),
                ("Logo Scale (0.1-0.5)", "--logo_scale"),
                ("Logo X (0.0-1.0)", "--logo_x"),
                ("Logo Y (0.0-1.0)", "--logo_y"),
                ("Logo Shadow (px)", "--logo_shadow"),
            ],
            "Perspective & Warp": [
                ("POV X (-1.0 to 1.0)", "--pov_x"),
                ("POV Y (-1.0 to 1.0)", "--pov_y"),
                ("Warp Strength", "--warp"),
                ("Tilt Degrees", "--tilt"),
                ("Offset X", "--offset_x"),
                ("Offset Y", "--offset_y"),
            ],
            "Focus & DoF": [
                ("Focus X (0.0 to 1.0)", "--focus_x"),
                ("Focus Y (0.0 to 1.0)", "--focus_y"),
                ("Focus Radius", "--focus_radius"),
                ("DoF Max Blur", "--dof_blur_max"),
                ("DoF Center X", "--dof_x"),
                ("DoF Center Y", "--dof_y"),
                ("DoF Falloff", "--dof_falloff"),
            ],
            "Effects": [
                ("Fade Left (0.0 to 1.0)", "--fade_left"),
                ("Fade Right (0.0 to 1.0)", "--fade_right"),
            ]
        }

        self.param_vars = {}
        for tab_name, fields in self.param_schema.items():
            tab = ttk.Frame(self.notebook, padding=10)
            self.notebook.add(tab, text=tab_name)

            tab.columnconfigure(1, weight=1)
            tab.columnconfigure(3, weight=1)

            for i, item in enumerate(fields):
                # Properly unpack the tuple instead of stringifying it
                l_text = item[0]
                cli_flag = item[1]
                options = item[2] if len(item) > 2 else None

                ttk.Label(tab, text=f"{l_text}:").grid(
                    row=i // 2, column=(i % 2) * 2, sticky="e", padx=5, pady=5
                )
                var = tk.StringVar()
                # Key is the CLI flag string, not the whole tuple
                self.param_vars[cli_flag] = var

                if options:
                    cb = ttk.Combobox(tab, textvariable=var, values=options, width=40)
                    cb.grid(row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=5)
                else:
                    ttk.Entry(tab, textvariable=var, width=12).grid(
                        row=i // 2, column=(i % 2) * 2 + 1, sticky="w", padx=5
                    )

        # --- Text Overlay & Preview ---
        frame_text = ttk.LabelFrame(self.scrollable_frame, text="4. Text Overlay & Preview", padding=10)
        frame_text.grid(row=3, column=0, sticky="ew", padx=10, pady=5)

        self.text_val = tk.StringVar()
        self.text_font = tk.StringVar(value="default")
        self.text_size = tk.DoubleVar(value=0.12)
        self.text_x = tk.DoubleVar(value=0.5)
        self.text_y = tk.DoubleVar(value=0.5)
        self.text_align = tk.StringVar(value="left")

        self.text_val.trace_add("write", self.update_preview)
        self.text_size.trace_add("write", self.update_preview)
        self.text_x.trace_add("write", self.update_preview)
        self.text_y.trace_add("write", self.update_preview)
        self.text_align.trace_add("write", self.update_preview)
        # FIX: Trace font changes so preview updates when a font is selected
        self.text_font.trace_add("write", self.update_preview)

        self.system_fonts = self.get_system_fonts()
        font_options = list(self.system_fonts.keys())
        font_options.remove("default")
        font_options = ["default"] + sorted(font_options, key=lambda x: x.lower())

        controls_frame = ttk.Frame(frame_text)
        controls_frame.pack(side="left", fill="both", expand=True)
        controls_frame.columnconfigure(1, weight=1)

        ttk.Label(controls_frame, text="Word/Phrase:").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Entry(controls_frame, textvariable=self.text_val, width=25).grid(
            row=0, column=1, columnspan=2, sticky="w", padx=5
        )

        ttk.Label(controls_frame, text="System Font:").grid(row=1, column=0, sticky="w", pady=5)
        self.font_combo = ttk.Combobox(
            controls_frame, textvariable=self.text_font, values=font_options, width=22
        )
        self.font_combo.grid(row=1, column=1, columnspan=2, sticky="w", padx=5)

        ttk.Label(controls_frame, text="Size (Scale):").grid(row=2, column=0, sticky="w", pady=5)
        ttk.Scale(controls_frame, from_=0.05, to=0.30, variable=self.text_size,
                  command=self.update_preview).grid(row=2, column=1, sticky="ew", padx=5)
        ttk.Spinbox(controls_frame, from_=0.05, to=0.30, increment=0.01,
                    textvariable=self.text_size, width=6).grid(row=2, column=2, sticky="w", padx=(0, 5))

        ttk.Label(controls_frame, text="Horizontal (X):").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Scale(controls_frame, from_=0.0, to=1.0, variable=self.text_x,
                  command=self.update_preview).grid(row=3, column=1, sticky="ew", padx=5)
        ttk.Spinbox(controls_frame, from_=0.0, to=1.0, increment=0.01,
                    textvariable=self.text_x, width=6).grid(row=3, column=2, sticky="w", padx=(0, 5))

        ttk.Label(controls_frame, text="Vertical (Y):").grid(row=4, column=0, sticky="w", pady=5)
        ttk.Scale(controls_frame, from_=0.0, to=1.0, variable=self.text_y,
                  command=self.update_preview).grid(row=4, column=1, sticky="ew", padx=5)
        ttk.Spinbox(controls_frame, from_=0.0, to=1.0, increment=0.01,
                    textvariable=self.text_y, width=6).grid(row=4, column=2, sticky="w", padx=(0, 5))

        ttk.Label(controls_frame, text="Alignment:").grid(row=5, column=0, sticky="w", pady=5)
        ttk.Combobox(controls_frame, textvariable=self.text_align,
                     values=["left", "center", "right"], width=10,
                     state="readonly").grid(row=5, column=1, sticky="w", padx=5)

        # Right Side (Live Canvas Preview)
        self.preview_w = 260
        self.preview_h = 146
        self.preview_canvas = tk.Canvas(
            frame_text, width=self.preview_w, height=self.preview_h,
            bg="#1a1c23", highlightthickness=1, highlightbackground="#444"
        )
        self.preview_canvas.pack(side="right", padx=10, pady=5)
        self.update_preview()

        # --- Output Options ---
        frame_output = ttk.LabelFrame(self.scrollable_frame, text="5. Output Options", padding=10)
        frame_output.grid(row=4, column=0, sticky="ew", padx=10, pady=5)
        frame_output.columnconfigure(1, weight=1)

        # Filename row
        ttk.Label(frame_output, text="Filename (optional):").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=(0, 8))
        self.filename_var = tk.StringVar()
        ttk.Entry(frame_output, textvariable=self.filename_var, width=40).grid(row=0, column=1, sticky="ew", pady=(0, 8))
        ttk.Label(frame_output, text="Leave blank for auto datetime name", foreground="gray").grid(row=0, column=2, sticky="w", padx=(8, 0), pady=(0, 8))

        # Resolution checkboxes
        res_frame = ttk.Frame(frame_output)
        res_frame.grid(row=1, column=0, columnspan=3, sticky="w")
        self.res_4k_var = tk.BooleanVar(value=False)
        self.res_1080p_var = tk.BooleanVar(value=False)
        self.res_720p_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(res_frame, text="Generate 4K (3840x2160)",
                        variable=self.res_4k_var).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(res_frame, text="Generate 1080p (1920x1080)",
                        variable=self.res_1080p_var).pack(side="left", padx=(0, 10))
        ttk.Checkbutton(res_frame, text="Generate 720p (1280x720)",
                        variable=self.res_720p_var).pack(side="left")

        # --- Action Buttons ---
        btn_frame = ttk.Frame(self.scrollable_frame)
        btn_frame.grid(row=5, column=0, pady=15)

        self.run_btn = ttk.Button(btn_frame, text="Generate Wallpaper", command=self.start_thread)
        self.run_btn.pack(side="left", padx=10)

        self.api_btn = ttk.Button(btn_frame, text="⚙️ Update API Keys", command=self.show_api_key_popup)
        self.api_btn.pack(side="left", padx=10)

        # Prompt for keys on startup if missing
        self.root.after(100, self.check_initial_keys)

        # --- Console Output ---
        frame_console = ttk.LabelFrame(self.scrollable_frame, text="Console Output", padding=5)
        frame_console.grid(row=6, column=0, sticky="nsew", padx=10, pady=5)
        self.scrollable_frame.rowconfigure(6, weight=1)
        self.console = tk.Text(frame_console, height=12, bg="#1e1e1e", fg="#00ff00",
                               font=("Consolas", 9))
        self.console.pack(fill="both", expand=True)

    def get_env_path(self):
        """Determine the correct path for the .env file whether running as a script or compiled exe."""
        if getattr(sys, 'frozen', False):
            # If packaged via PyInstaller, save .env next to the executable
            return Path(sys.executable).parent / ".env"
        else:
            # If running locally, save it in the project root
            return Path(__file__).resolve().parent.parent / ".env"

    def check_initial_keys(self):
        """Check if TMDB API key exists on load. If not, force the popup."""
        env_path = self.get_env_path()
        load_dotenv(dotenv_path=env_path)
        
        # TMDB is strictly required to run the tool
        if not os.getenv("TMDB_API_KEY"):
            self.show_api_key_popup(force=True)

    def show_api_key_popup(self, force=False):
        """Displays the API key entry and validation popup."""
        popup = tk.Toplevel(self.root)
        popup.title("API Configuration")
        popup.geometry("500x260")
        popup.grab_set()  # Make it modal (blocks the main window)
        popup.resizable(False, False)
        
        # If forced on startup, closing the window without saving closes the app
        if force:
            popup.protocol("WM_DELETE_WINDOW", lambda: self.root.destroy())

        ttk.Label(popup, text="Please enter your API Keys to continue:", font=("Arial", 11, "bold")).pack(pady=(15, 5))
        
        env_path = self.get_env_path()
        load_dotenv(dotenv_path=env_path, override=True)

        frame = ttk.Frame(popup, padding=10)
        frame.pack(fill="both", expand=True)

        # Inputs
        ttk.Label(frame, text="TMDb API Key (*):").grid(row=0, column=0, sticky="w", pady=5)
        tmdb_var = tk.StringVar(value=os.getenv("TMDB_API_KEY", ""))
        ttk.Entry(frame, textvariable=tmdb_var, width=45).grid(row=0, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(frame, text="Fanart.tv Key:").grid(row=1, column=0, sticky="w", pady=5)
        fanart_var = tk.StringVar(value=os.getenv("FANART_API_KEY", ""))
        ttk.Entry(frame, textvariable=fanart_var, width=45).grid(row=1, column=1, sticky="w", padx=10, pady=5)

        ttk.Label(frame, text="MDBList Key:").grid(row=2, column=0, sticky="w", pady=5)
        mdblist_var = tk.StringVar(value=os.getenv("MDBLIST_API_KEY", ""))
        ttk.Entry(frame, textvariable=mdblist_var, width=45).grid(row=2, column=1, sticky="w", padx=10, pady=5)

        status_lbl = ttk.Label(popup, text="", foreground="red", justify="center")
        status_lbl.pack(pady=5)

        def save_and_validate():
            status_lbl.config(text="Validating keys over network...", foreground="#007ACC")
            popup.update()

            t = tmdb_var.get().strip()
            f = fanart_var.get().strip()
            m = mdblist_var.get().strip()

            errors = []
            
            # --- 1. Validate TMDB (Required) ---
            if not t:
                errors.append("TMDb API Key is required.")
            else:
                try:
                    res = requests.get("https://api.themoviedb.org/3/configuration", params={"api_key": t}, timeout=5)
                    if res.status_code != 200:
                        errors.append("TMDb API Key is invalid.")
                except requests.RequestException:
                    errors.append("Network error connecting to TMDb.")

            # --- 2. Validate Fanart (Optional) ---
            if f:
                try:
                    res = requests.get("https://webservice.fanart.tv/v3/movies/latest", params={"api_key": f}, timeout=5)
                    if res.status_code == 401:
                        errors.append("Fanart API Key is invalid.")
                except requests.RequestException:
                    errors.append("Network error connecting to Fanart.tv.")

            # --- 3. Validate MDBList (Optional) ---
            if m:
                try:
                    # Test against a known public user list to verify the token works
                    res = requests.get("https://api.mdblist.com/lists/user/mdblist", params={"apikey": m}, timeout=5)
                    if res.status_code in (401, 403):
                        errors.append("MDBList API Key is invalid.")
                except requests.RequestException:
                    errors.append("Network error connecting to MDBList.")

            # --- Handle Results ---
            if errors:
                status_lbl.config(text="\n".join(errors), foreground="red")
            else:
                # Keys are good! Save them to .env
                if not env_path.exists():
                    env_path.touch()
                
                set_key(env_path, "TMDB_API_KEY", t)
                set_key(env_path, "FANART_API_KEY", f)
                set_key(env_path, "MDBLIST_API_KEY", m)

                status_lbl.config(text="Keys verified and saved successfully!", foreground="green")
                popup.update()

                # Unlock the popup closing logic and destroy it
                if force:
                    popup.protocol("WM_DELETE_WINDOW", popup.destroy)
                popup.after(1000, popup.destroy)

        ttk.Button(popup, text="Save & Validate", command=save_and_validate).pack(pady=(0, 10))

    def get_system_fonts(self):
        fonts_dict = {"default": "default"}
        sys_name = platform.system()
        font_dirs = []

        if sys_name == "Windows":
            font_dirs.append(Path(os.environ.get('WINDIR', 'C:\\Windows')) / 'Fonts')
            local_app_data = os.environ.get('LOCALAPPDATA')
            if local_app_data:
                font_dirs.append(Path(local_app_data) / 'Microsoft\\Windows\\Fonts')
        elif sys_name == "Darwin":
            font_dirs.extend([
                Path('/Library/Fonts'),
                Path('/System/Library/Fonts'),
                Path.home() / 'Library/Fonts'
            ])
        else:  # Linux
            font_dirs.extend([
                Path('/usr/share/fonts'),
                Path('/usr/local/share/fonts'),
                Path.home() / '.fonts',
                Path.home() / '.local/share/fonts'
            ])

        for d in font_dirs:
            if d.exists():
                for ext in ('*.ttf', '*.ttc', '*.otf'):
                    for font_path in d.rglob(ext):
                        fonts_dict[font_path.name] = str(font_path)

        return fonts_dict

    def _on_mousewheel(self, event):
        # FIX: Handle all platforms correctly
        if event.num == 4:          # Linux scroll up
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:        # Linux scroll down
            self.canvas.yview_scroll(1, "units")
        elif platform.system() == "Windows":
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        else:                       # macOS
            self.canvas.yview_scroll(int(-1 * event.delta), "units")

    def toggle_mode(self):
        mode = self.mode_var.get()

        # Hide all sub-frames first
        self.sort_frame.pack_forget()
        self.type_frame.pack_forget()
        self.curated_frame.pack_forget()
        self.input_entry.pack_forget()

        if mode == "mdblist":
            self.input_entry.pack(fill="x", pady=5)
            self.sort_frame.pack(fill="x", pady=5)
        elif mode == "tmdb":
            self.input_entry.pack(fill="x", pady=5)
            self.type_frame.pack(fill="x", pady=5)
        else:  # curated
            self.curated_frame.pack(fill="x", pady=5)

    def update_preview(self, *args):
        try:
            px = self.text_x.get()
            py = self.text_y.get()
            scale = self.text_size.get()
        except tk.TclError:
            return

        text = self.text_val.get()
        if not text:
            text = "(Preview)"

        img = Image.new("RGB", (self.preview_w, self.preview_h), "#2c3e50")
        draw = ImageDraw.Draw(img)
        draw.ellipse([-50, -50, 100, 100], fill="#34495e")

        selected_font = self.text_font.get().strip()
        resolved_font_path = self.system_fonts.get(selected_font, selected_font)
        preview_font_size = max(8, int(self.preview_h * scale * 1.5))
        font = None

        if resolved_font_path != "default":
            try:
                font = ImageFont.truetype(resolved_font_path, preview_font_size)
            except Exception:
                pass

        if font is None:
            for fallback in [
                "arialbd.ttf", "arial.ttf",
                "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            ]:
                try:
                    font = ImageFont.truetype(fallback, preview_font_size)
                    break
                except Exception:
                    pass

        if font is None:
            try:
                font = ImageFont.load_default(size=preview_font_size)
            except TypeError:
                font = ImageFont.load_default()

        try:
            left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
            tw = right - left
            th = bottom - top
        except AttributeError:
            tw, th = draw.textsize(text, font=font)

        align = self.text_align.get()
        if align == "center":
            x_pos = int(self.preview_w * px) - (tw // 2)
        elif align == "right":
            x_pos = int(self.preview_w * px) - tw
        else:
            x_pos = int(self.preview_w * px)

        y_pos = int(self.preview_h * py) - th
        shadow_offset = max(1, int(preview_font_size * 0.05))

        draw.text((x_pos + shadow_offset, y_pos + shadow_offset), text, font=font, fill=(0, 0, 0))
        draw.text((x_pos, y_pos), text, font=font, fill=(255, 255, 255))

        self.preview_photo = ImageTk.PhotoImage(img)
        self.preview_canvas.delete("all")
        self.preview_canvas.create_image(0, 0, image=self.preview_photo, anchor="nw")

    def log(self, message):
        self.console.insert(tk.END, message)
        self.console.see(tk.END)

    def start_thread(self):
        mode = self.mode_var.get()
        # Curated mode needs no text input — keyword comes from the dropdown
        if mode != "curated":
            inputs = self.input_entry.get().strip()
            if not inputs:
                messagebox.showwarning("Missing Input", "Please provide at least one URL or ID.")
                return

        if not self.res_4k_var.get() and not self.res_1080p_var.get() and not self.res_720p_var.get():
            messagebox.showwarning("Missing Resolution", "Please select at least one resolution to generate.")
            return

        self.run_btn.config(state="disabled")
        self.console.delete(1.0, tk.END)
        threading.Thread(target=self.run_script, daemon=True).start()

    def run_script(self):
        base_dir = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        engine_path = os.path.join(base_dir, "wallpaper_engine.py")

        cmd = [sys.executable, "-u", engine_path, "--style", self.style_var.get()]
        mode = self.mode_var.get()

        if mode == "mdblist":
            inputs = self.input_entry.get().strip().split()
            cmd.extend(["--url"] + inputs)
            sort_val = self.sort_var.get().strip()
            if sort_val:
                cmd.extend(["--sort", sort_val])
        elif mode == "curated":
            keyword = self.curated_var.get().strip()
            cmd.extend(["--type", "curated", "--id", keyword])
        else:  # tmdb
            inputs = self.input_entry.get().strip().split()
            cmd.extend(["--id"] + inputs + ["--type", self.type_var.get()])

        res_list = []
        if self.res_4k_var.get():
            res_list.append("4k")
        if self.res_1080p_var.get():
            res_list.append("1080p")
        if self.res_720p_var.get():
            res_list.append("720p")
        if res_list:
            cmd.extend(["--res"] + res_list)

        text_val = self.text_val.get().strip()
        selected_font = self.text_font.get().strip()
        resolved_font_path = self.system_fonts.get(selected_font, selected_font)
        if text_val:
            cmd.extend([
                "--text_overlay", text_val,
                "--text_pos_x", str(round(self.text_x.get(), 3)),
                "--text_pos_y", str(round(self.text_y.get(), 3)),
                "--text_font", resolved_font_path,
                "--text_scale", str(round(self.text_size.get(), 3)),
                "--text_align", self.text_align.get()
            ])

        for flag, var in self.param_vars.items():
            val = var.get().strip()
            if val:
                cmd.extend([flag, val])

        filename_val = self.filename_var.get().strip()
        if filename_val:
            cmd.extend(["--filename", filename_val])

        # --- NEW: Build and display parameter summary in console ---
        param_log = [
            "\n=== Generation Parameters ===",
            f"Style: {self.style_var.get()}",
            f"Mode: {mode}"
        ]

        if mode == "mdblist":
            param_log.append(f"Input: {self.input_entry.get().strip()}")
            param_log.append(f"Sort: {self.sort_var.get()}")
        elif mode == "curated":
            param_log.append(f"Keyword: {self.curated_var.get()}")
        else:
            param_log.append(f"Input IDs: {self.input_entry.get().strip()}")
            param_log.append(f"TMDb Type: {self.type_var.get()}")

        param_log.append(f"Resolutions: {', '.join(res_list) if res_list else 'None'}")

        if text_val:
            param_log.append(f"Text Overlay: '{text_val}' (Font: {selected_font}, Size: {self.text_size.get()}, X: {self.text_x.get()}, Y: {self.text_y.get()}, Align: {self.text_align.get()})")

        # Capture only the advanced overrides that are actually filled out
        advanced_overrides = [f"{flag.lstrip('-')}: {var.get().strip()}" for flag, var in self.param_vars.items() if var.get().strip()]
        if advanced_overrides:
            param_log.append("Advanced Overrides:")
            for override in advanced_overrides:
                param_log.append(f"  - {override}")

        if filename_val:
            param_log.append(f"Custom Filename: {filename_val}")

        param_log.append("=============================\n")

        # Output to GUI console
        self.log("\n".join(param_log) + "\n")
        self.log(f"Executing CLI: {' '.join(cmd)}\n")
        self.log("-" * 60 + "\n")

        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8'
            )
            for line in process.stdout:
                self.root.after(0, self.log, line)

            process.wait()
            self.root.after(0, self.log, f"\nDone! (Exit code: {process.returncode})\n")
        except Exception as e:
            self.root.after(0, self.log, f"\nError: {str(e)}\n")
        finally:
            self.root.after(0, lambda: self.run_btn.config(state="normal"))


if __name__ == "__main__":
    root = tk.Tk()
    app = WallpaperGUI(root)
    root.mainloop()