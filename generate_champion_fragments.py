import json
import re
import sqlite3
import os
import shutil
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(r"c:\Users\trues\OneDrive\Desktop\Advaith\F1 Results database, upgraded\sessionresults.db")

# Output Directories
DRIVERS_DIR = ROOT / "drivers"
CONSTRUCTORS_DIR = ROOT / "constructors"
DRIVERS_UNDIVIDED = ROOT / "drivers_undivided"
CONSTRUCTORS_UNDIVIDED = ROOT / "constructors_undivided"

def clean_slug(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

def get_latest_race_info():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT ID, Season FROM GrandsPrix ORDER BY ID DESC LIMIT 1")
    race = cur.fetchone()
    
    cur.execute("""
        SELECT DISTINCT d.Name 
        FROM GrandPrixResults r 
        JOIN Drivers d ON r.driverid = d.ID 
        WHERE r.grandprixid = ?
    """, (race[0],))
    driver_entrants = {r[0] for r in cur.fetchall()}
    
    cur.execute("""
        SELECT DISTINCT c.ConstructorName 
        FROM GrandPrixResults r 
        JOIN Constructors c ON r.constructorid = c.ID 
        WHERE r.grandprixid = ?
    """, (race[0],))
    constructor_entrants = {r[0] for r in cur.fetchall()}
    
    conn.close()
    return race[0], race[1], driver_entrants, constructor_entrants

def fetch_stats(table: str, name_col: str):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(f"SELECT {name_col}, Championships, Wins, Podiums, Poles, Points, Starts, Entries FROM {table}")
    stats = {row[name_col]: dict(row) for row in cur.fetchall()}
    conn.close()
    return stats

def calculate_rarity_score(s: dict) -> float:
    return 25 * s["Championships"] + 10 * s["Wins"] + 6 * s["Podiums"] + 5.5 * s["Poles"] + 0.2 * s["Points"] + 0.1 * s["Starts"] + 0.05 * s["Entries"]

def get_fragment_count(stats: dict) -> int:
    if stats["Championships"] > 0:
        return 4
    if stats["Wins"] > 0:
        return 2
    return 1

def process_images(type_name: str, stats_dict: dict, entrants: set, source_dir: Path, undivided_dir: Path, output_json: str, base_url: str):
    undivided_dir.mkdir(exist_ok=True)
    manifest = []
    
    # 1. Group files by entity (slug)
    files_by_entity = {}
    for f in source_dir.glob("*.webp"):
        stem = f.stem
        # Check if it's a fragment
        is_fragment = False
        base = stem
        for suffix in ["-top-left", "-top-right", "-bottom-left", "-bottom-right", "-left", "-right", "-full"]:
            if stem.endswith(suffix):
                base = stem[:-len(suffix)]
                is_fragment = True
                break
        
        # Check for numeric suffix like _1
        base_name = base
        if "_" in base:
            parts = base.rsplit("_", 1)
            if parts[1].isdigit():
                base_name = parts[0]
        
        # Use slug instead of direct name for the key
        entity_key = clean_slug(base_name)
        files_by_entity.setdefault(entity_key, {"raw": [], "fragments": {}} )
        if is_fragment:
            files_by_entity[entity_key]["fragments"][stem] = f
        else:
            files_by_entity[entity_key]["raw"].append(f)

    # 2. Process each entity
    for s_name, stats in stats_dict.items():
        found_data = files_by_entity.get(clean_slug(s_name))
        if not found_data:
            continue
            
        count = get_fragment_count(stats)
        slug = clean_slug(s_name)
        
        # Determine if we should recompute
        # Rules:
        # - Champions: 4 frags
        # - Winners: 2 frags
        # - Everyone else: 1 frag (raw)
        
        fragments = []
        
        # Case A: We have raw images
        if found_data["raw"]:
            for i, raw_path in enumerate(found_data["raw"]):
                current_slug = f"{slug}-{i+1}" if len(found_data["raw"]) > 1 else slug
                
                # Copy to undivided if not champion (as per user instruction)
                if stats["Championships"] == 0:
                    shutil.copy2(raw_path, undivided_dir / f"{current_slug}.webp")
                
                with Image.open(raw_path) as img:
                    w, h = img.size
                    if count == 4:
                        boxes = [
                            ("top-left", (0, 0, w//2, h//2)),
                            ("top-right", (w//2, 0, w, h//2)),
                            ("bottom-left", (0, h//2, w//2, h)),
                            ("bottom-right", (w//2, h//2, w, h)),
                        ]
                    elif count == 2:
                        boxes = [
                            ("left", (0, 0, w//2, h)),
                            ("right", (w//2, 0, w, h)),
                        ]
                    else:
                        boxes = [("full", (0, 0, w, h))]
                    
                    for suffix, box in boxes:
                        frag_name = f"{current_slug}-{suffix}.webp"
                        frag_path = source_dir / frag_name
                        img.crop(box).save(frag_path, format="WEBP", quality=80)
                        fragments.append(f"{base_url}/{type_name}/{frag_name}")
        
        # Case B: We ONLY have existing fragments (likely champions)
        elif found_data["fragments"]:
            # If we don't have raw, we just list the fragments we found
            for frag_stem in sorted(found_data["fragments"].keys()):
                fragments.append(f"{base_url}/{type_name}/{frag_stem}.webp")

        if fragments:
            manifest.append({
                "name": s_name,
                "category": "World Champions" if stats["Championships"] > 0 else "Race Winners" if stats["Wins"] > 0 else "Others",
                "fragments": fragments,
                "searchKeywords": s_name,
                "rarityScore": calculate_rarity_score(stats)
            })

    output_file = ROOT / output_json
    output_file.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Generated {len(manifest)} entries for {type_name}")

def main():
    race_id, season, d_entrants, c_entrants = get_latest_race_info()
    print(f"Latest Race: {race_id} ({season})")
    
    d_stats = fetch_stats("Drivers", "Name")
    c_stats = fetch_stats("Constructors", "ConstructorName")
    
    process_images("drivers", d_stats, d_entrants, DRIVERS_DIR, DRIVERS_UNDIVIDED, "drivers.json", "https://mclarenmp4-22.github.io")
    process_images("constructors", c_stats, c_entrants, CONSTRUCTORS_DIR, CONSTRUCTORS_UNDIVIDED, "constructors.json", "https://mclarenmp4-22.github.io")

if __name__ == "__main__":
    main()
