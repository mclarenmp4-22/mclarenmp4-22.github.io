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
    # Handle accents and special characters (e.g., Räikkönen -> raikkonen)
    import unicodedata
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
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

def process_images(type_name: str, stats_dict: dict, entrants: set, source_dir: Path, output_dir: Path, output_json: str, base_url: str):
    output_dir.mkdir(exist_ok=True)
    source_dir.mkdir(exist_ok=True)
    manifest = []
    
    # Track all valid files in this run
    valid_files = set()

    # 1. Group files by entity (slug) from ALL folders (undivided and primary)
    files_by_entity = {}
    
    # Check undivided and main output dir for raw images
    for folder in [source_dir, output_dir]:
        for f in folder.glob("*.webp"):
            stem = f.stem
            # Ignore fragment files when looking for raw images
            is_frag = False
            for suffix in ["-top-left", "-top-right", "-bottom-left", "-bottom-right", "-left", "-right", "-full"]:
                if stem.endswith(suffix):
                    is_frag = True
                    break
            if is_frag:
                continue

            base_name = stem
            if "_" in stem:
                parts = stem.rsplit("_", 1)
                if parts[1].isdigit():
                    base_name = parts[0]
            
            entity_key = clean_slug(base_name)
            files_by_entity.setdefault(entity_key, {"raw": [], "fragments": {}} )
            if f not in files_by_entity[entity_key]["raw"]:
                files_by_entity[entity_key]["raw"].append(f)

    # Check output folder for existing fragments
    for f in output_dir.glob("*.webp"):
        stem = f.stem
        base = stem
        is_fragment = False
        for suffix in ["-top-left", "-top-right", "-bottom-left", "-bottom-right", "-left", "-right", "-full"]:
            if stem.endswith(suffix):
                base = stem[:-len(suffix)]
                is_fragment = True
                break
        
        if is_fragment:
            entity_key = clean_slug(base)
            files_by_entity.setdefault(entity_key, {"raw": [], "fragments": {}} )
            files_by_entity[entity_key]["fragments"][stem] = f

    # 2. Process each entity
    for s_name, stats in stats_dict.items():
        entity_key = clean_slug(s_name)
        found_data = files_by_entity.get(entity_key)
        if not found_data:
            continue
            
        target_count = get_fragment_count(stats)
        is_recent_entrant = s_name in entrants
        
        fragments = []
        
        # Decide if we need to re-fragment/rename/standardize
        needs_refragment = is_recent_entrant or not found_data["fragments"]
        
        # Standardize check: If existing fragments don't match the new lowercase-hyphenated key, we re-fragment
        if not needs_refragment and found_data["fragments"]:
            # If any existing fragment doesn't start with the correct slug, re-save them
            first_frag = next(iter(found_data["fragments"].keys()))
            if not first_frag.startswith(entity_key + "-"):
                needs_refragment = True
            
            # Count check
            if not needs_refragment and len(found_data["raw"]) == 1 and len(found_data["fragments"]) != target_count:
                needs_refragment = True

        if needs_refragment and found_data["raw"]:
            for i, raw_path in enumerate(found_data["raw"]):
                current_slug = f"{entity_key}-{i+1}" if len(found_data["raw"]) > 1 else entity_key
                
                with Image.open(raw_path) as img:
                    w, h = img.size
                    if target_count == 4:
                        boxes = [("top-left", (0, 0, w//2, h//2)), ("top-right", (w//2, 0, w, h//2)), ("bottom-left", (0, h//2, w//2, h)), ("bottom-right", (w//2, h//2, w, h))]
                    elif target_count == 2:
                        boxes = [("left", (0, 0, w//2, h)), ("right", (w//2, 0, w, h))]
                    else:
                        boxes = [("full", (0, 0, w, h))]
                    
                    for suffix, box in boxes:
                        frag_name = f"{current_slug}-{suffix}.webp"
                        img.crop(box).save(output_dir / frag_name, format="WEBP", quality=80)
                        fragments.append(f"{base_url}/{type_name}/{frag_name}")
                        valid_files.add(frag_name)
        else:
            # Reuse existing fragments, but standardize names (e.g., Alain_Prost -> alain-prost)
            if found_data["fragments"]:
                for frag_stem in sorted(found_data["fragments"].keys()):
                    # Identify the suffix
                    suffix = ""
                    for s in ["-top-left", "-top-right", "-bottom-left", "-bottom-right", "-left", "-right", "-full"]:
                        if frag_stem.endswith(s):
                            suffix = s
                            break
                    
                    # Construct new name
                    new_frag_name = f"{entity_key}{suffix}.webp"
                    old_path = output_dir / f"{frag_stem}.webp"
                    new_path = output_dir / new_frag_name
                    
                    if old_path.exists() and old_path != new_path:
                        print(f"Renaming fragment {old_path.name} -> {new_frag_name}")
                        old_path.replace(new_path)
                    
                    fragments.append(f"{base_url}/{type_name}/{new_frag_name}")
                    valid_files.add(new_frag_name)
            elif found_data["raw"]:
                for i, raw_path in enumerate(found_data["raw"]):
                    current_slug = f"{entity_key}-{i+1}" if len(found_data["raw"]) > 1 else entity_key
                    frag_name = f"{current_slug}-full.webp"
                    shutil.copy2(raw_path, output_dir / frag_name)
                    fragments.append(f"{base_url}/{type_name}/{frag_name}")
                    valid_files.add(frag_name)

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

    # Cleanup: Remove any .webp files in output_dir NOT in valid_files
    for f in output_dir.glob("*.webp"):
        if f.name not in valid_files:
            f.unlink()


def main():
    race_id, season, d_entrants, c_entrants = get_latest_race_info()
    print(f"Latest Race: {race_id} ({season})")
    
    d_stats = fetch_stats("Drivers", "Name")
    c_stats = fetch_stats("Constructors", "ConstructorName")
    
    process_images("drivers", d_stats, d_entrants, DRIVERS_UNDIVIDED, DRIVERS_DIR, "drivers.json", "https://mclarenmp4-22.github.io")
    process_images("constructors", c_stats, c_entrants, CONSTRUCTORS_UNDIVIDED, CONSTRUCTORS_DIR, "constructors.json", "https://mclarenmp4-22.github.io")

if __name__ == "__main__":
    main()
