#!/usr/bin/env python3
"""
wallpaper_engine.py
Unified generator for T1 (Landscape) and T2 (Mixed) grid wallpapers.
Supports both 3D perspective warp and Flat layouts.
"""

import io
import math
import os
import sys
import time
import random
import argparse
import re
import threading
from pathlib import Path
from datetime import datetime

import requests
import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from dotenv import load_dotenv

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                        CONFIGURATION                              ║
# ╚═══════════════════════════════════════════════════════════════════╝

env_path = Path(__file__).resolve().parent / ".env"
if not env_path.exists():
    env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

TMDB_API_KEY = os.getenv("TMDB_API_KEY")
FANART_API_KEY = os.getenv("FANART_API_KEY")
MDBLIST_API_KEY = os.getenv("MDBLIST_API_KEY")

# -- Global Processing Options
FETCH_COUNT = 60
ACCENT_COLOR = None
_DEFAULT_ACCENT = (20, 60, 80)
_ACCENT_MAP = {}

# -- Shared Layout Geometry
GAP = 8
CARD_RADIUS = 8
FADE_LEFT = 0.30
FADE_RIGHT = 1.00
DOF_BLUR_MAX = 10.0
DOF_FALLOFF = 1.5
PRIORITY_ZONE = 0.55

# ── Style Profiles ──────────────────────────────────────────────────────────
STYLE_PROFILES = {
    "t1_3d": {
        "layout": "t1",
        "landscape_w": 400, "portrait_w": None,
        "pov_x": 1.0, "pov_y": -1.0, "warp": 0.37,
        "tilt": -10, "offset_x": 170, "offset_y": -80,
        "focus_x": 0.7, "focus_y": 0.2, "focus_radius": 0.35,
        "dof_x": 0.75, "dof_y": 0.25
    },
    "t1_flat": {
        "layout": "t1",
        "landscape_w": 400, "portrait_w": None,
        "pov_x": 0.0, "pov_y": 0.0, "warp": 0.0,
        "tilt": -10, "offset_x": 170, "offset_y": -80,
        "focus_x": 0.75, "focus_y": 0.5, "focus_radius": 0.35,
        "dof_x": 0.75, "dof_y": 0.25
    },
    "t2_3d": {
        "layout": "t2",
        "landscape_w": 300, "portrait_w": 200,
        "pov_x": 1.0, "pov_y": -1.0, "warp": 0.37,
        "tilt": -10, "offset_x": 335, "offset_y": 100,
        "focus_x": 0.75, "focus_y": 0.25, "focus_radius": 0.30,
        "dof_x": 0.75, "dof_y": 0.25
    },
    "t2_flat": {
        "layout": "t2",
        "landscape_w": 300, "portrait_w": 200,
        "pov_x": 0.0, "pov_y": 0.0, "warp": 0.0,
        "tilt": -10, "offset_x": 335, "offset_y": 100,
        "focus_x": 0.5, "focus_y": 0.0, "focus_radius": 0.30,
        "dof_x": 0.75, "dof_y": 0.25
    }
}

# ╔═══════════════════════════════════════════════════════════════════╗
# ║                       INTERNAL CODE                               ║
# ╚═══════════════════════════════════════════════════════════════════╝

TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMG_BASE = "https://image.tmdb.org/t/p"
BACKDROP_SIZE = "w1280"
POSTER_SIZE = "w780"
FANART_BASE = "https://webservice.fanart.tv/v3"

BLOCKED_KEYWORDS = [
    "hentai", "porn", "pornography", "erotica", "xxx",
    "av girl", "jav", "milf", "fetish", "bondage",
    "bdsm", "ecchi", "yaoi", "yuri", "uncensored", "creampie", "bukkake"
]
BLOCKED_IDS = {1241752, 95897}

def _normalize_text(text):
    text = text.lower()
    text = re.sub(r"[_\-.]", " ", text)
    return re.sub(r"\s+", " ", text).strip()

def _is_adult_content(item):
    if item.get("id") in BLOCKED_IDS or item.get("adult") is True: return True
    if item.get("vote_count", 0) < 15 and item.get("popularity", 0) < 5: return True
    texts = [item.get("title", ""), item.get("name", ""), item.get("original_title", ""), item.get("original_name", ""), item.get("overview", "")]
    for text in texts:
        text = _normalize_text(text)
        for word in BLOCKED_KEYWORDS:
            if word in text or re.search(r"\b" + re.escape(word) + r"\b", text): return True
    combined = " ".join(texts).lower()
    for pattern in [r"\b[a-z]{2,5}-\d{2,5}\b", r"\bfc2\b", r"\b\d{6,}\b"]:
        if re.search(pattern, combined): return True
    return False

def _tmdb(endpoint, params=None):
    if not TMDB_API_KEY: return {}
    p = dict(params or {})
    p.update({"api_key": TMDB_API_KEY, "include_adult": False})
    try:
        r = requests.get(f"{TMDB_BASE}{endpoint}", params=p, timeout=15)
        if r.status_code != 200: return {}
        data = r.json()
        if "results" in data:
            data["results"] = [item for item in data["results"] if not _is_adult_content(item)]
        return data
    except Exception: return {}

def _pull_media(media_type, extra, count, config):
    items = []
    for page in range(1, 11):
        params = {
            "sort_by": config.get("tmdb_sort", "popularity.desc"),
            "page": page,
            "language": config.get("tmdb_lang", "en-US"),
            "include_adult": False,
            **extra
        }
        if config.get("tmdb_year"):
            if media_type == "movie": params["primary_release_year"] = config["tmdb_year"]
            else: params["first_air_date_year"] = config["tmdb_year"]
        if config.get("tmdb_vote_min") is not None:
            params["vote_average.gte"] = config["tmdb_vote_min"]
        if config.get("tmdb_vote_count") is not None:
            params["vote_count.gte"] = config["tmdb_vote_count"]
            
        data = _tmdb(f"/discover/{media_type}", params)
        for item in data.get("results", []):
            if item.get("backdrop_path") or item.get("poster_path"): items.append((media_type, item))
        if len(items) >= count: break
        if page >= data.get("total_pages", 1): break
    return items[:count]

def _calculate_focal_score(item):
    pop = float(item.get("popularity", 0))
    date_str = item.get("release_date") or item.get("first_air_date") or ""
    if not date_str: return pop
    try:
        release_date = datetime.strptime(date_str, "%Y-%m-%d")
        age_days = max(1, (datetime.now() - release_date).days)
        return pop * (1.0 + (1200.0 / (age_days + 100)))
    except ValueError: return pop

def fetch_titles(tmdb_id, id_type, count, config):
    items, target_id = [], str(tmdb_id).lower().strip()
    only_movies, only_tv = "-movies" in target_id, "-tv" in target_id
    clean_id = target_id.replace("-movies", "").replace("-tv", "")

    if id_type == "curated":
        MOVIE_ENDPOINTS = {
            "now_playing":  "/movie/now_playing",
            "upcoming":     "/movie/upcoming",
            "popular":      "/movie/popular",
            "top_rated":    "/movie/top_rated",
        }
        TV_ENDPOINTS = {
            "airing_today": "/tv/airing_today",
            "on_the_air":   "/tv/on_the_air",
            "popular":      "/tv/popular",
            "top_rated":    "/tv/top_rated",
        }

        def _fetch_paginated(endpoint, media_type, n):
            results = []
            for page in range(1, 11):
                data = _tmdb(endpoint, {"page": page, "language": config.get("tmdb_lang", "en-US")})
                for item in data.get("results", []):
                    if item.get("backdrop_path") or item.get("poster_path"):
                        results.append((media_type, item))
                if len(results) >= n or page >= data.get("total_pages", 1):
                    break
            return results[:n]

        combined = []

        if clean_id.startswith("trending"):
            parts = clean_id.split("-")
            window = "day"
            for p in parts:
                if p in ("day", "week"):
                    window = p
            if not only_tv:
                combined += _fetch_paginated(f"/trending/movie/{window}", "movie", count)
            if not only_movies:
                combined += _fetch_paginated(f"/trending/tv/{window}", "tv", count)
        else:
            if clean_id in MOVIE_ENDPOINTS and not only_tv:
                combined += _fetch_paginated(MOVIE_ENDPOINTS[clean_id], "movie", count)
            if clean_id in TV_ENDPOINTS and not only_movies:
                combined += _fetch_paginated(TV_ENDPOINTS[clean_id], "tv", count)
            if clean_id not in MOVIE_ENDPOINTS and clean_id not in TV_ENDPOINTS and not clean_id.startswith("trending"):
                sys.exit(f"  Error: Unknown curated keyword '{clean_id}'.")

    elif id_type == "network": combined = _pull_media("tv", {"with_networks": clean_id}, count, config)
    elif id_type == "company": combined = ([] if only_movies else _pull_media("tv", {"with_companies": clean_id}, count, config)) + ([] if only_tv else _pull_media("movie", {"with_companies": clean_id}, count, config))
    elif id_type == "provider": combined = ([] if only_movies else _pull_media("tv", {"with_watch_providers": clean_id, "watch_region": "US"}, count, config)) + ([] if only_tv else _pull_media("movie", {"with_watch_providers": clean_id, "watch_region": "US"}, count, config))
    elif id_type == "genre": combined = ([] if only_tv else _pull_media("movie", {"with_genres": clean_id}, count, config)) + ([] if only_movies else _pull_media("tv", {"with_genres": clean_id}, count, config))
    
    elif id_type == "person":
        num_match = re.search(r'\d+', clean_id)
        numeric_id = num_match.group() if num_match else clean_id
        
        combined = []
        
        # 1. Fetch explicitly tagged images of the actor (guaranteed to be them)
        tagged_data = _tmdb(f"/person/{numeric_id}/tagged_images")
        for idx, item in enumerate(tagged_data.get("results", [])):
            path = item.get("file_path")
            if path:
                aspect_ratio = item.get("aspect_ratio", 1.0)
                combined.append(("movie", {
                    "id": f"{numeric_id}_tagged_{item.get('id', idx)}",
                    "poster_path": path if aspect_ratio < 1 else None,
                    "backdrop_path": path if aspect_ratio >= 1 else None,
                    "popularity": 10000 - idx  # Massive boost so these appear first
                }))
                
        # 2. Fill the remaining grid slots with their top movies and shows
        credits_data = _tmdb(f"/person/{numeric_id}/combined_credits")
        for item in credits_data.get("cast", []):
            kind = item.get("media_type", "movie")
            if item.get("backdrop_path") or item.get("poster_path"):
                combined.append((kind, item))
    else: 
        sys.exit(1)

    combined_sorted = sorted(combined, key=lambda kt: kt[1].get("popularity", 0), reverse=True)
    seen = set()
    for k, item in combined_sorted:
        item_id = item.get("id")
        if item_id and item_id not in seen:
            seen.add(item_id)
            items.append((k, item))
            if len(items) >= count: break
    return items

def _fetch_label(tmdb_id, id_type):
    name = ""
    num_match = re.search(r'\d+', str(tmdb_id))
    numeric_id = num_match.group() if num_match else tmdb_id
    
    try:
        if id_type == "network": name = _tmdb(f"/network/{numeric_id}").get("name", "")
        elif id_type == "company": name = _tmdb(f"/company/{numeric_id}").get("name", "")
        elif id_type == "provider":
            for ep in ("/watch/providers/tv", "/watch/providers/movie"):
                match = next((p for p in _tmdb(ep, {"watch_region": "US"}).get("results", []) if str(p.get("provider_id")) == str(numeric_id)), None)
                if match: name = match.get("provider_name", ""); break
        elif id_type == "genre":
            all_g = _tmdb("/genre/movie/list", {"language": "en-US"}).get("genres", []) + _tmdb("/genre/tv/list", {"language": "en-US"}).get("genres", [])
            name = next((g["name"] for g in all_g if str(g["id"]) == str(numeric_id)), "")
        elif id_type == "person":
            # This endpoint strictly gets the profile text data to set the filename safely
            name = _tmdb(f"/person/{numeric_id}").get("name", "")
    except Exception: pass
    
    safe = re.sub(r"[^\w]+", "_", name.strip().lower()).strip("_")
    return safe or f"{id_type}_{numeric_id}"

def fetch_mdblist_items(url, count, sort=None, mediatype="all"):
    url = url.strip().rstrip("/")
    m = re.search(r"mdblist\.com/lists/([^/]+)/([^/]+)$", url) or re.match(r"^([^/\s]+)/([^/\s]+)$", url)
    if not m: raise ValueError(f"Could not parse MDBList URL: {url!r}")
    username, slug = m.group(1), m.group(2)
    label = re.sub(r"[^\w]+", "_", slug.strip().lower()).strip("_") or f"{username}_{slug}"
    
    print(f"  Fetching MDBList: {username}/{slug} ...")
    try:
        user_lists = requests.get(f"https://api.mdblist.com/lists/user/{username}", params={"apikey": MDBLIST_API_KEY}, timeout=20).json()
        list_id = next((l["id"] for l in user_lists if l.get("slug", "").lower() == slug.lower()), None)
        if not list_id: sys.exit(f"  Error: List '{slug}' not found.")
        
        params = {"apikey": MDBLIST_API_KEY, "limit": max(count * 3, 150)}
        if sort:
            parts = sort.lower().split(".")
            params.update({"sort": parts[0], "order": parts[1] if len(parts) > 1 else "desc"})
        if mediatype != "all":
            params["mediatype"] = mediatype

        data = requests.get(f"https://api.mdblist.com/lists/{list_id}/items", params=params, timeout=20).json()
        raw_items = data if isinstance(data, list) else data.get("movies", []) + data.get("shows", [])
        print(f"  Found {len(raw_items)} items. Cross-referencing with TMDB...")
    except Exception as e: sys.exit(f"  Error: MDBList API Error: {e}")

    results = []
    for entry in raw_items:
        imdb_id = entry.get("imdb_id") or entry.get("imdb")
        if not imdb_id: continue
        kind = "tv" if entry.get("mediatype") == "show" else "movie"
        try:
            hits = _tmdb(f"/find/{imdb_id}", {"external_source": "imdb_id"}).get("tv_results" if kind == "tv" else "movie_results", [])
            if hits:
                hit_item = hits[0]
                if hit_item.get("backdrop_path") or hit_item.get("poster_path"):
                    results.append((kind, hit_item))
        except Exception: continue
        if len(results) >= count: break
    return label, results

def resolve_image(kind, item, prefer_poster=False):
    tmdb_id, url = item["id"], None
    if prefer_poster and item.get("poster_path"): url = f"{TMDB_IMG_BASE}/{POSTER_SIZE}{item['poster_path']}"
    else:
        if FANART_API_KEY:
            try:
                fanart_data = requests.get(f"{FANART_BASE}/{'tv' if kind=='tv' else 'movies'}/{_tmdb(f'/tv/{tmdb_id}/external_ids').get('tvdb_id') if kind=='tv' else tmdb_id}", params={"api_key": FANART_API_KEY}, timeout=15).json()
                keys = ["tvthumb", "showbackground"] if kind == "tv" else ["moviethumb", "moviebackground"]
                for key in keys:
                    en = [c for c in fanart_data.get(key, []) if c.get("lang") == "en"]
                    if en: url = sorted(en, key=lambda c: int(c.get("likes", 0)), reverse=True)["url"]; break
            except Exception: pass
        if not url and item.get("backdrop_path"): url = f"{TMDB_IMG_BASE}/{BACKDROP_SIZE}{item['backdrop_path']}"
        if not url and item.get("poster_path"): url = f"{TMDB_IMG_BASE}/{POSTER_SIZE}{item['poster_path']}"

    if not url: return None
    for attempt in range(3):
        try:
            return Image.open(io.BytesIO(requests.get(url, timeout=20).content)).convert("RGBA")
        except Exception:
            if attempt == 2: return None
            time.sleep(1)

def _make_tile(img, tw, th, opacity=1.0, config=None):
    iw, ih = img.size
    tr, sr = tw / th, iw / ih
    if sr > tr: nw = int(ih * tr); img = img.crop(((iw - nw) // 2, 0, (iw - nw) // 2 + nw, ih))
    else: nh = int(iw / tr); img = img.crop((0, (ih - nh) // 2, iw, (ih - nh) // 2 + nh))
    img = img.resize((tw, th), Image.LANCZOS)
    r = max(2, int(CARD_RADIUS * tw / max(config["landscape_w"], 1)))
    mask = Image.new("L", (tw, th), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, tw-1, th-1], radius=r, fill=255)
    out = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    out.paste(img, mask=mask)
    if opacity < 1.0:
        rc, gc, bc, ac = out.split()
        out = Image.merge("RGBA", (rc, gc, bc, ac.point(lambda v: int(v * opacity))))
    return out

# ── Unified Layout Engine ───────────────────────────────────────────────────

def _build_layout(portrait_imgs, landscape_imgs, canvas_w, canvas_h, scale, config):
    if config["layout"] == "t1":
        return _build_layout_t1(landscape_imgs, canvas_w, canvas_h, scale, config)
    else:
        return _build_layout_t2(portrait_imgs, landscape_imgs, canvas_w, canvas_h, scale, config)

def _build_layout_t1(landscape_imgs, canvas_w, canvas_h, scale, config):
    lw = int(config["landscape_w"] * scale)
    lh = int(round(lw * 9 / 16))
    gap = int(GAP * scale)

    bleed_x = (lw + gap) * 3
    bleed_y = lh * 2 + gap * 4
    stagger_x = (lw + gap) // 2

    over_w, over_h = canvas_w + bleed_x * 2, canvas_h + bleed_y * 2
    ox, oy = bleed_x, bleed_y
    canvas = Image.new("RGBA", (over_w, over_h), (10, 12, 16, 255))

    l_cutoff = max(1, int(len(landscape_imgs) * 0.35))
    pri_landscapes, rest_landscapes = landscape_imgs[:l_cutoff], landscape_imgs[l_cutoff:]
    rng = random.Random(42)
    tiles_to_place = []

    y, row_idx = -bleed_y + oy, 0
    while y < over_h:
        x = -bleed_x + (stagger_x if row_idx % 2 == 1 else 0) + ox
        while x < over_w:
            screen_x, screen_y = x - ox + (lw * 0.5), y - oy + (lh * 0.5)
            norm_x, norm_y = screen_x / canvas_w, screen_y / canvas_h
            opacity = FADE_LEFT + (FADE_RIGHT - FADE_LEFT) * max(0.0, min(1.0, norm_x))
            is_focal = math.hypot(norm_x - config["focus_x"], norm_y - config["focus_y"]) <= config["focus_radius"]
            is_on_screen = (0.0 <= norm_x <= 1.0) and (0.0 <= norm_y <= 1.0)
            
            tiles_to_place.append({"x": x, "y": y, "w": lw, "h": lh, "opacity": opacity, "is_focal": is_focal, "is_on_screen": is_on_screen})
            x += lw + gap
        y += lh + gap; row_idx += 1

    tiles_to_place.sort(key=lambda t: (not t["is_on_screen"], not t["is_focal"]))
    unique_pri, unique_rest = list(reversed(pri_landscapes)), list(reversed(rest_landscapes))
    repeat_pri, repeat_rest = list(pri_landscapes), list(rest_landscapes)
    rng.shuffle(repeat_pri); rng.shuffle(repeat_rest)
    pri_idx, rest_idx = 0, 0

    for t in tiles_to_place:
        if t["is_focal"]:
            fallback = repeat_pri if repeat_pri else repeat_rest
            src = unique_pri.pop() if unique_pri else fallback[pri_idx % len(fallback)]
            if not unique_pri: pri_idx += 1
        else:
            fallback = repeat_rest if repeat_rest else repeat_pri
            src = unique_rest.pop() if unique_rest else fallback[rest_idx % len(fallback)]
            if not unique_rest: rest_idx += 1
            
        img_src = src["img"] if isinstance(src, dict) else src
        tile = _make_tile(img_src, t["w"], t["h"], opacity=t["opacity"], config=config)
        canvas.paste(tile, (int(t["x"]), int(t["y"])), tile)

    return canvas, ox, oy

def _build_layout_t2(portrait_imgs, landscape_imgs, canvas_w, canvas_h, scale, config):
    lw = int(config["landscape_w"] * scale)
    pw = int(config["portrait_w"] * scale)
    lh, ph = int(round(lw * 9 / 16)), int(round(pw * 3 / 2))
    gap = int(GAP * scale)

    bleed_x = (lw + gap) * 3
    bleed_y = max(ph, lh) * 2 + gap * 4
    over_w, over_h = canvas_w + bleed_x * 2, canvas_h + bleed_y * 2
    ox, oy = bleed_x, bleed_y
    canvas = Image.new("RGBA", (over_w, over_h), (10, 12, 16, 255))

    rng, columns, x, pi = random.Random(42), [], -bleed_x, 0
    COL_PATTERN = ["L", "P", "L", "P", "L", "P", "L", "P", "L"]
    
    while x < canvas_w + bleed_x:
        ct = COL_PATTERN[pi % len(COL_PATTERN)]
        base_w = lw if ct == "L" else pw
        if config["pov_x"] != 0:
            scale_factor = 1.0 - (config["pov_x"] * ((x + base_w * 0.5 - canvas_w/2) / (canvas_w/2)) * 0.15)
            cw = int(base_w * max(0.5, min(1.5, scale_factor)))
        else: cw = base_w
        columns.append({"x": x, "w": cw, "type": ct})
        x += cw + gap; pi += 1

    p_cutoff, l_cutoff = max(1, int(len(portrait_imgs) * 0.35)), max(1, int(len(landscape_imgs) * 0.35))
    pri_port, rest_port = portrait_imgs[:p_cutoff], portrait_imgs[p_cutoff:]
    pri_land, rest_land = landscape_imgs[:l_cutoff], landscape_imgs[l_cutoff:]

    tiles_to_place = []
    for col_i, col in enumerate(columns):
        y = -bleed_y + (int(ph * 0.35) if col_i % 2 == 1 else 0) + oy
        while y < over_h:
            tile_type = ("P" if col["type"] == "L" else "L") if rng.random() < 0.35 else col["type"]
            th = max(4, int(col["w"] * 3 / 2)) if tile_type == "P" else max(4, int(col["w"] * 9 / 16))
            norm_x, norm_y = (col["x"] + col["w"]/2) / canvas_w, (y - oy + th/2) / canvas_h
            opacity = FADE_LEFT + (FADE_RIGHT - FADE_LEFT) * max(0.0, min(1.0, norm_x))
            is_focal = math.hypot(norm_x - config["focus_x"], norm_y - config["focus_y"]) <= config["focus_radius"]
            is_on_screen = (0.0 <= norm_x <= 1.0) and (0.0 <= norm_y <= 1.0)
            
            tiles_to_place.append({"x": col["x"] + ox, "y": y, "w": col["w"], "h": th, "type": tile_type, "is_focal": is_focal, "is_on_screen": is_on_screen, "opacity": opacity})
            y += th + gap

    tiles_to_place.sort(key=lambda t: (not t["is_on_screen"], not t["is_focal"]))
    placed_ids = set()

    def pick_next(src_list, fallback, placed, idx):
        for i, item in enumerate(src_list):
            if item["id"] not in placed: placed.add(item["id"]); return src_list.pop(i), idx
        if fallback: item = fallback[idx % len(fallback)]; placed.add(item["id"]); return item, idx + 1
        return None, idx

    idxs = {"pri_L": 0, "rest_L": 0, "pri_P": 0, "rest_P": 0}
    for t in tiles_to_place:
        if t["type"] == "L": src, idxs["pri_L" if t["is_focal"] else "rest_L"] = pick_next(pri_land if t["is_focal"] else rest_land, pri_land if t["is_focal"] else rest_land, placed_ids, idxs["pri_L" if t["is_focal"] else "rest_L"])
        else: src, idxs["pri_P" if t["is_focal"] else "rest_P"] = pick_next(pri_port if t["is_focal"] else rest_port, pri_port if t["is_focal"] else rest_port, placed_ids, idxs["pri_P" if t["is_focal"] else "rest_P"])
        
        if src:
            tile = _make_tile(src["img"], t["w"], t["h"], opacity=t["opacity"], config=config)
            canvas.paste(tile, (int(t["x"]), int(t["y"])), tile)

    return canvas, ox, oy

# ── Post-Processing ─────────────────────────────────────────────────────────

def _perspective_warp(oversized, ox, oy, out_w, out_h, config):
    pov_x, pov_y, warp, tilt = config["pov_x"], config["pov_y"], config["warp"], config["tilt"]
    
    if pov_x == 0.0 and pov_y == 0.0:
        scale = out_w / 1920.0
        shifted_ox = ox - int(config["offset_x"] * scale)
        shifted_oy = oy - int(config["offset_y"] * scale)
        if tilt != 0:
            rotated = oversized.rotate(-tilt, resample=Image.BICUBIC, center=(shifted_ox + out_w / 2, shifted_oy + out_h / 2))
            return rotated.crop((shifted_ox, shifted_oy, shifted_ox + out_w, shifted_oy + out_h))
        return oversized.crop((shifted_ox, shifted_oy, shifted_ox + out_w, shifted_oy + out_h))

    tl_y, bl_y, tr_y, br_y = 0.0, float(out_h), 0.0, float(out_h)
    tl_x, bl_x, tr_x, br_x = 0.0, 0.0, float(out_w), float(out_w)

    if pov_x > 0: inset = (out_h * warp * abs(pov_x)) / 2; tl_y += inset; bl_y -= inset
    elif pov_x < 0: inset = (out_h * warp * abs(pov_x)) / 2; tr_y += inset; br_y -= inset
    if pov_y > 0: inset = (out_w * warp * abs(pov_y)) / 2; tl_x += inset; tr_x -= inset
    elif pov_y < 0: inset = (out_w * warp * abs(pov_y)) / 2; bl_x += inset; br_x -= inset

    src = [(ox, oy), (ox + out_w, oy), (ox + out_w, oy + out_h), (ox, oy + out_h)]
    dst = [(tl_x, tl_y), (tr_x, tr_y), (br_x, br_y), (bl_x, bl_y)]

    A, b = [], []
    for (sx, sy), (dx, dy) in zip(src, dst):
        A.extend([[dx, dy, 1, 0, 0, 0, -sx*dx, -sx*dy], [0, 0, 0, dx, dy, 1, -sy*dx, -sy*dy]])
        b.extend([sx, sy])

    try:
        coeffs = np.linalg.solve(np.array(A, dtype=np.float64), np.array(b, dtype=np.float64))
        return oversized.transform((out_w, out_h), Image.PERSPECTIVE, tuple(coeffs), resample=Image.BICUBIC)
    except Exception: return oversized.crop((ox, oy, ox + out_w, oy + out_h))

def _apply_dof(image, scale, config):
    if DOF_BLUR_MAX <= 0: return image
    w, h, N, max_r = *image.size, 5, DOF_BLUR_MAX * scale
    xg, yg = np.meshgrid(np.linspace(0, w-1, w, dtype=np.float32), np.linspace(0, h-1, h, dtype=np.float32))
    blur_map = np.clip((np.sqrt((xg - config["dof_x"] * w)**2 + (yg - config["dof_y"] * h)**2) / math.hypot(w, h)) ** DOF_FALLOFF, 0.0, 1.0)
    
    layers = [image if (i/N)*max_r < 0.5 else image.filter(ImageFilter.GaussianBlur(radius=(i/N)*max_r)) for i in range(N + 1)]
    arrs = [np.array(l, dtype=np.float32) for l in layers]
    out = np.zeros_like(arrs[0])

    for i in range(N):
        in_ = (blur_map >= i/N) & (blur_map < (i+1)/N)
        t = ((blur_map - i/N) / (1/N + 1e-9))[in_]
        out[in_] = arrs[i][in_] * (1 - t[:, None]) + arrs[i+1][in_] * t[:, None]
    out[blur_map >= (N-1)/N] = arrs[N][blur_map >= (N-1)/N]
    return Image.fromarray(out.clip(0, 255).astype(np.uint8))

def _apply_gradient(canvas, accent, show_gradient=True):
    if not show_gradient: return canvas
    w, h = canvas.size
    result = Image.alpha_composite(canvas, Image.new("RGBA", (w, h), (0, 0, 0, 0))) 
    
    left_img = Image.new("RGBA", (w//4, h//4), (0, 0, 0, 0))
    px = left_img.load()
    for x in range(int(w//4 * 0.65)):
        a = int(240 * ((1.0 - x / (w//4 * 0.65)) ** 1.4))
        if a:
            for y in range(h // 4):
                px[x, y] = (6, 8, 12, a)
    result = Image.alpha_composite(result, left_img.resize((w, h), Image.BILINEAR))
    
    glow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dw = ImageDraw.Draw(glow)
    for i in range(18):
        rr, aa = int(math.hypot(w, h) * (0.05 + 0.38 * (i/18))), int(14 * (1 - i/18) ** 2.2)
        if aa: dw.ellipse([w - rr, -rr, w + rr, rr], fill=(*accent, aa))
    return Image.alpha_composite(result, glow)

def _apply_text_overlay(image, text, px=0.5, py=0.5, font_name="default", font_scale=0.12, align="left"):
    if not text: return image
    draw = ImageDraw.Draw(image)
    w, h = image.size
    font_size = max(10, int(h * font_scale))
    
    font = None
    if font_name and font_name.lower() != "default" and os.path.exists(font_name):
        try: font = ImageFont.truetype(font_name, font_size)
        except Exception: pass
        
    if not font:
        for fallback in ["arialbd.ttf", "arial.ttf", "/System/Library/Fonts/Helvetica.ttc", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]:
            try: 
                font = ImageFont.truetype(fallback, font_size)
                break
            except Exception: pass
            
    if not font: font = ImageFont.load_default()
    
    try:
        left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
        tw = right - left
        th = bottom - top
    except AttributeError:
        tw, th = draw.textsize(text, font=font)
        left, top = 0, 0
    
    if align == "center": x = int(w * px) - (tw // 2)
    elif align == "right": x = int(w * px) - tw
    else: x = int(w * px)
    y = int(h * py) - th
    
    draw.text((x, y), text, font=font, fill=(255, 255, 255, 255))
    return image

def _save(canvas, path):
    final = canvas.convert("RGB")
    final.save(path, "JPEG", quality=95, optimize=True)
    print(f"  Saved:  {path}  ({final.size[0]}x{final.size[1]},  {os.path.getsize(path) / 1_048_576:.1f} MB)")

# ── Main Controller ─────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Unified Wallpaper Generator")
    parser.add_argument("--style", required=True, choices=STYLE_PROFILES.keys())
    parser.add_argument("--id", nargs="+", default=None)
    parser.add_argument("--type", default=None)
    parser.add_argument("--url", nargs="+", default=None)
    parser.add_argument("--sort", default="score.desc")
    parser.add_argument("--output_dir", default=None, help="Directory to save output files (default: 'wallpapers' folder in the parent directory)")
    parser.add_argument("--filename", default=None, help="Base filename without extension (default: datetime_style)")
    parser.add_argument("--no-gradient", action="store_true")
    
    parser.add_argument("--res", nargs="+", choices=["4k", "1080p", "720p"], default=["4k", "1080p"], help="Resolutions to generate")
    
    # Text
    parser.add_argument("--text_overlay", type=str, default=None)
    parser.add_argument("--text_pos_x", type=float, default=0.5)
    parser.add_argument("--text_pos_y", type=float, default=0.5)
    parser.add_argument("--text_font", type=str, default="default")
    parser.add_argument("--text_scale", type=float, default=0.12)
    parser.add_argument("--text_align", type=str, default="left", choices=["left", "center", "right"])

    # API Filters
    parser.add_argument("--tmdb_sort", type=str, default=None)
    parser.add_argument("--tmdb_year", type=int, default=None)
    parser.add_argument("--tmdb_lang", type=str, default=None)
    parser.add_argument("--tmdb_vote_min", type=float, default=None)
    parser.add_argument("--tmdb_vote_count", type=int, default=None)
    parser.add_argument("--mdblist_mediatype", type=str, default="all", choices=["all", "movie", "show"])

    # Layout & Scale
    parser.add_argument("--fetch_count", type=int, default=None)
    parser.add_argument("--landscape_w", type=int, default=None)
    parser.add_argument("--portrait_w", type=int, default=None)
    parser.add_argument("--gap", type=int, default=None)
    parser.add_argument("--card_radius", type=int, default=None)
    
    # Perspective & Warp
    parser.add_argument("--pov_x", type=float, default=None)
    parser.add_argument("--pov_y", type=float, default=None)
    parser.add_argument("--warp", type=float, default=None)
    parser.add_argument("--tilt", type=int, default=None)
    parser.add_argument("--offset_x", type=int, default=None)
    parser.add_argument("--offset_y", type=int, default=None)
    
    # Focus & DoF
    parser.add_argument("--focus_x", type=float, default=None)
    parser.add_argument("--focus_y", type=float, default=None)
    parser.add_argument("--focus_radius", type=float, default=None)
    parser.add_argument("--dof_blur_max", type=float, default=None)
    parser.add_argument("--dof_x", type=float, default=None)
    parser.add_argument("--dof_y", type=float, default=None)
    parser.add_argument("--dof_falloff", type=float, default=None)

    # Effects
    parser.add_argument("--fade_left", type=float, default=None)
    parser.add_argument("--fade_right", type=float, default=None)
    
    args = parser.parse_args()

    config = STYLE_PROFILES[args.style].copy()
    
    if args.landscape_w is not None: config["landscape_w"] = args.landscape_w
    if args.portrait_w is not None: config["portrait_w"] = args.portrait_w
    if args.pov_x is not None: config["pov_x"] = args.pov_x
    if args.pov_y is not None: config["pov_y"] = args.pov_y
    if args.warp is not None: config["warp"] = args.warp
    if args.tilt is not None: config["tilt"] = args.tilt
    if args.offset_x is not None: config["offset_x"] = args.offset_x
    if args.offset_y is not None: config["offset_y"] = args.offset_y
    if args.focus_x is not None: config["focus_x"] = args.focus_x
    if args.focus_y is not None: config["focus_y"] = args.focus_y
    if args.focus_radius is not None: config["focus_radius"] = args.focus_radius
    if args.dof_x is not None: config["dof_x"] = args.dof_x
    if args.dof_y is not None: config["dof_y"] = args.dof_y
    
    # API Filters Assignment
    if args.tmdb_sort is not None: config["tmdb_sort"] = args.tmdb_sort
    if args.tmdb_year is not None: config["tmdb_year"] = args.tmdb_year
    if args.tmdb_lang is not None: config["tmdb_lang"] = args.tmdb_lang
    if args.tmdb_vote_min is not None: config["tmdb_vote_min"] = args.tmdb_vote_min
    if args.tmdb_vote_count is not None: config["tmdb_vote_count"] = args.tmdb_vote_count

    if args.fetch_count is not None: globals()["FETCH_COUNT"] = args.fetch_count
    if args.gap is not None: globals()["GAP"] = args.gap
    if args.card_radius is not None: globals()["CARD_RADIUS"] = args.card_radius
    if args.dof_blur_max is not None: globals()["DOF_BLUR_MAX"] = args.dof_blur_max
    if args.dof_falloff is not None: globals()["DOF_FALLOFF"] = args.dof_falloff
    if args.fade_left is not None: globals()["FADE_LEFT"] = args.fade_left
    if args.fade_right is not None: globals()["FADE_RIGHT"] = args.fade_right

    use_mdblist = bool(args.url)
    use_curated = (not use_mdblist) and args.type == "curated"

    # curated mode: --id is optional; if omitted default to "trending"
    if use_curated and not args.id:
        args.id = ["trending"]

    if not use_mdblist and not use_curated and (not args.id or not args.type):
        sys.exit("  Error: Provide --url  OR  --type curated [--id <keyword>]  OR  --id <id> --type <type>")

    accent = _DEFAULT_ACCENT
    OUT_DIR = Path(args.output_dir) if args.output_dir else Path(__file__).resolve().parent.parent / "wallpapers"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Determine base filename — user-supplied or datetime + style
    if args.filename and args.filename.strip():
        # Sanitise: strip extension, replace bad chars
        base_name = re.sub(r'[\\/*?:"<>|]', "_", args.filename.strip())
        base_name = base_name.rsplit(".", 1)[0] if "." in base_name else base_name
    else:
        base_name = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{args.style}"

    if use_mdblist:
        print(f"\n  Mode   : MDBList\n  URLs   : {', '.join(args.url)}\n")
        list_of_results, labels = [], []
        for url in args.url:
            lbl, tits = fetch_mdblist_items(url, FETCH_COUNT, sort=args.sort, mediatype=args.mdblist_mediatype)
            labels.append(lbl)
            list_of_results.append(tits)
            
        seen, titles = set(), []
        while len(titles) < FETCH_COUNT:
            added = False
            for tits in list_of_results:
                if len(titles) >= FETCH_COUNT: break
                while tits:
                    kind, item = tits.pop(0)
                    if item["id"] not in seen:
                        seen.add(item["id"])
                        titles.append((kind, item))
                        added = True
                        break
            if not added: break
            
        label = "_".join(labels)[:80]
    else:
        labels, combined = [_fetch_label(tid, args.type) for tid in args.id], []
        for tid in args.id: 
            combined.extend(fetch_titles(tid, args.type, FETCH_COUNT, config))
        titles = sorted(combined, key=lambda ki: _calculate_focal_score(ki[1]), reverse=True)[:FETCH_COUNT]
        label = "_".join(labels)
        brand_name = re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')

    out_dir = OUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    
    print("Downloading images...")
    portrait_imgs, landscape_imgs, fail_n = [], [], 0
    for i, (kind, item) in enumerate(titles):
        sys.stdout.write(f"  [{i+1:02d}/{len(titles)}] Fetching...\r"); sys.stdout.flush()
        land = resolve_image(kind, item, prefer_poster=False)
        port = resolve_image(kind, item, prefer_poster=True)
        
        if config["layout"] == "t1":
            if land: landscape_imgs.append({"id": item["id"], "img": land})
            else: fail_n += 1
        else:
            if land: landscape_imgs.append({"id": item["id"], "img": land})
            if port: portrait_imgs.append({"id": item["id"], "img": port})
            if not land and not port: fail_n += 1

    if config["layout"] == "t2":
        if not portrait_imgs: portrait_imgs = landscape_imgs[:]
        if not landscape_imgs: landscape_imgs = portrait_imgs[:]
        
        split_idx = max(1, int(len(portrait_imgs)*0.35))
        portrait_imgs = portrait_imgs[:split_idx] + random.sample(portrait_imgs[split_idx:], len(portrait_imgs[split_idx:]))
    
    if not landscape_imgs and not portrait_imgs:
        sys.exit("\n  Error: No images were successfully downloaded. Check your API keys, network, or provided IDs/URLs.")
        
    if "4k" in args.res:
        print("\nCompositing 4K...")
        over4k, ox4k, oy4k = _build_layout(portrait_imgs, landscape_imgs, 3840, 2160, 2.0, config)
        dof4k = _apply_dof(_perspective_warp(over4k, ox4k, oy4k, 3840, 2160, config), 2.0, config)
        
        final_4k = _apply_gradient(dof4k, accent, not args.no_gradient)
        if args.text_overlay: final_4k = _apply_text_overlay(final_4k, args.text_overlay, args.text_pos_x, args.text_pos_y, args.text_font, args.text_scale, args.text_align)
        _save(final_4k, out_dir / f"{base_name}_4k.jpg")

    if "1080p" in args.res:
        print("\nCompositing 1080p...")
        over1080, ox1080, oy1080 = _build_layout(portrait_imgs, landscape_imgs, 1920, 1080, 1.0, config)
        dof1080 = _apply_dof(_perspective_warp(over1080, ox1080, oy1080, 1920, 1080, config), 1.0, config)
        
        final_1080 = _apply_gradient(dof1080, accent, not args.no_gradient)
        if args.text_overlay: final_1080 = _apply_text_overlay(final_1080, args.text_overlay, args.text_pos_x, args.text_pos_y, args.text_font, args.text_scale, args.text_align)
        _save(final_1080, out_dir / f"{base_name}_1080p.jpg")

    if "720p" in args.res:
        print("\nCompositing 720p...")
        over720, ox720, oy720 = _build_layout(portrait_imgs, landscape_imgs, 1280, 720, 0.667, config)
        dof720 = _apply_dof(_perspective_warp(over720, ox720, oy720, 1280, 720, config), 0.667, config)

        final_720 = _apply_gradient(dof720, accent, not args.no_gradient)
        if args.text_overlay: final_720 = _apply_text_overlay(final_720, args.text_overlay, args.text_pos_x, args.text_pos_y, args.text_font, args.text_scale, args.text_align)
        _save(final_720, out_dir / f"{base_name}_720p.jpg")

if __name__ == "__main__":
    main()