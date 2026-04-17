"""
F1 Image Scraper — Bing Images (no API key, direct scrape)
Pulls driver names from the Drivers table, searches Bing Images,
filters by resolution, crops to 1280x720 (16:9).

Usage:
    pip install requests Pillow numpy beautifulsoup4
    python f1_image_scraper.py --db path/to/f1.db
"""

import os
import random
import re
import sys
import time
import json
import sqlite3
import requests
import numpy as np
from PIL import Image
from io import BytesIO
from bs4 import BeautifulSoup

# ─── CONFIG ───────────────────────────────────────────────────────────────────

DRIVER_LIMIT = 500
MIN_WIDTH = 1000
MIN_HEIGHT = 600
OUTPUT_WIDTH = 1000
OUTPUT_HEIGHT = 600
MAX_IMAGES_PER_DRIVER = 10
CHECK_DIR = "constructors"
OUTPUT_DIR = "constructors_undivided"

# Image search query templates for each driver
QUERY_TEMPLATES = [
    "{} F1 car on track, racing",
    "{} F1 Team",
    "{} Formula One car on track, racing",
    "{} Formula One car on track",
    "{} in an F1 car",
    "{} F1 car racing",
    "{} in F1 car",    
    "{} Grand Prix",
]

# Domains known to watermark their images — skip any URL containing these
WATERMARKED_DOMAINS = [
    "gettyimages", "shutterstock", "alamy", "dreamstime", "istockphoto",
    "depositphotos", "123rf", "pond5", "masterfile", "superstock",
    "imagebroker", "panthermedia", "fotolia", "adobestock", "wireimage",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/122.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ──────────────────────────────────────────────────────────────────────────────


def get_drivers_from_db() -> list:
    conn = sqlite3.connect("sessionresults.db")
    cur = conn.cursor()
    cur.execute("""
        SELECT ConstructorName, Starts
        FROM Constructors
        WHERE Wins > 0 AND indy500only = 0
    """,)
    rows = cur.fetchall()
    random.shuffle(rows)
    rows = rows[:DRIVER_LIMIT]
    conn.close()
    return rows


def search_bing_images(query: str, count: int = 15) -> list[str]:
    """Scrape Bing Images and return a list of direct image URLs."""
    search_url = "https://www.bing.com/images/search"
    params = {"q": query, "form": "HDRSC2", "first": 1, "count": count}

    try:
        resp = requests.get(search_url, params=params, headers=HEADERS, timeout=10)
        resp.raise_for_status()
    except Exception as e:
        print(f"  [!] Bing request failed: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    urls = []
    # Bing stores image metadata in JSON inside 'm' attributes on <a class="iusc">
    for tag in soup.find_all("a", class_="iusc"):
        m = tag.get("m")
        if not m:
            continue
        try:
            data = json.loads(m)
            url = data.get("murl")  # 'murl' = full resolution image URL
            if url and url.startswith("http"):
                urls.append(url)
        except Exception:
            continue

    return urls


def fetch_image(url: str):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content)).convert("RGB")
        return img
    except Exception:
        return None


def color_analysis_filter(img: Image.Image) -> bool:
    small = img.resize((200, 112))
    pixels = np.array(small).reshape(-1, 3).astype(float)
    brightness = pixels.mean(axis=1)
    if (brightness > 220).mean() > 0.60:
        return False
    if (brightness < 30).mean() > 0.70:
        return False
    if pixels.std(axis=0).mean() < 15:
        return False
    return True


def crop_to_16x9(img: Image.Image) -> Image.Image:
    w, h = img.size
    target_ratio = OUTPUT_WIDTH / OUTPUT_HEIGHT
    if (w / h) > target_ratio:
        new_w = int(h * target_ratio)
        left = (w - new_w) // 2
        img = img.crop((left, 0, left + new_w, h))
    else:
        new_h = int(w / target_ratio)
        top = (h - new_h) // 3
        img = img.crop((0, top, w, top + new_h))
    return img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.LANCZOS)


def sanitize(name: str) -> str:
    # Handle accents and special characters
    import unicodedata
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")


def process_driver(driver_name: str) -> int:
    driver_slug = sanitize(driver_name)

    # Check both folders (fragments in CHECK_DIR and raw in OUTPUT_DIR)
    found_in = None
    for folder in [CHECK_DIR, OUTPUT_DIR]:
        if os.path.exists(folder):
            # Check for any file starting with driver_slug (matches slug-fragment or slug_raw)
            existing = [f for f in os.listdir(folder) if f.startswith(driver_slug)]
            if len(existing) >= 1:
                found_in = folder
                break

    if found_in:
        print(f"\n⏭️  {driver_name} — already exists in {found_in}, skipping")
        return 1

    print(f"\n🔍 {driver_name}")

    saved = 0
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    for query_template in QUERY_TEMPLATES:
        if saved >= MAX_IMAGES_PER_DRIVER:
            break
        
        query = query_template.format(driver_name)
        print(f"  🔎 '{query}'")

        urls = search_bing_images(query, count=MAX_IMAGES_PER_DRIVER * 5)
        print(f"    📥 {len(urls)} URLs found")

        for i, url in enumerate(urls):
            if saved >= MAX_IMAGES_PER_DRIVER:
                break

            if any(d in url.lower() for d in WATERMARKED_DOMAINS):
                print(f"    [{i+1}] ✗ watermarked domain, skipping")
                continue

            img = fetch_image(url)
            if img is None:
                print(f"    [{i+1}] ✗ Failed to fetch")
                continue

            w, h = img.size
            print(f"    [{i+1}] {w}x{h}", end="")

            if w < MIN_WIDTH or h < MIN_HEIGHT:
                print(f"  ↷ too small")
                continue

            if not color_analysis_filter(img):
                print(f"  ✗ color filter")
                continue

            cropped = crop_to_16x9(img)
            # Use underscore for multiple images if needed, but keep it clear
            out_name = f"{driver_slug}_{saved + 1}.webp"
            out_path = os.path.join(OUTPUT_DIR, out_name)
            cropped.save(out_path, format="WEBP", quality=80)
            print(f"  ✅ saved as {out_name} in {OUTPUT_DIR}")
            saved += 1
            time.sleep(0.3)

    print(f"  → {saved} saved for {driver_name}")
    return saved


def scrape():
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    print(f"\n🏎  F1 Image Scraper — Bing Images")
    print(f"{'─' * 55}")

    drivers = get_drivers_from_db()
    print(f"Drivers (RANDOM):")
    for name, starts in drivers:
        print(f"  • {name} ({starts} starts)")
    print(f"{'─' * 55}")

    total = sum(process_driver(name) for name, _ in drivers)

    print(f"\n{'─' * 55}")
    print(f"✅ Done! {total} images saved to {os.path.abspath(OUTPUT_DIR)}/")


if __name__ == "__main__":
    scrape()



