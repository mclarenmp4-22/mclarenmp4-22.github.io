import json
import re
import sqlite3
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(r"c:\Users\trues\OneDrive\Desktop\Advaith\F1 Results database, upgraded\sessionresults.db")


def display_name_from_file(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"[_!]+$", "", stem)
    stem = re.sub(r"_(\d+)$", "", stem)
    stem = re.sub(r"[_!]+$", "", stem)
    stem = stem.replace("_", " ").strip()
    return stem


def clean_stem(path: Path) -> str:
    stem = path.stem
    stem = re.sub(r"[_!]+$", "", stem)
    stem = re.sub(r"_(\d+)$", "", stem)
    stem = re.sub(r"[_!]+$", "", stem)
    stem = re.sub(r"_+", "_", stem).strip("_")
    return stem


def file_slug(path: Path) -> str:
    stem = clean_stem(path)
    stem = stem.lower()
    stem = stem.replace("_", "-")
    stem = re.sub(r"[^a-z0-9-]+", "-", stem)
    stem = re.sub(r"-+", "-", stem).strip("-")
    return stem


def text_slug(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def source_images(folder: Path) -> list[Path]:
    images = []
    for path in sorted(folder.glob("*.webp")):
        if path.stem.endswith(("-top-left", "-top-right", "-bottom-left", "-bottom-right")):
            continue
        images.append(path)
    return images


def quarter_boxes(width: int, height: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    mid_x = width // 2
    mid_y = height // 2
    return [
        ("top-left", (0, 0, mid_x, mid_y)),
        ("top-right", (mid_x, 0, width, mid_y)),
        ("bottom-left", (0, mid_y, mid_x, height)),
        ("bottom-right", (mid_x, mid_y, width, height)),
    ]


def calculate_rarity_score(championships: int, wins: int, podiums: int, poles: int, points: float, starts: int, entries: int) -> float:
    """Calculate rarityScore based on the formula:
    25*Championships + 10*Wins + 6*Podiums + 5.5*Poles + 0.2*Points + 0.1*Starts + 0.05*Entries
    """
    return 25 * championships + 10 * wins + 6 * podiums + 5.5 * poles + 0.2 * points + 0.1 * starts + 0.05 * entries


def fetch_driver_stats() -> dict[str, dict]:
    """Fetch driver statistics from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT Name, Championships, Wins, Podiums, Poles, Points, Starts, Entries
        FROM Drivers
        WHERE Championships > 0
        ORDER BY Name
    """)
    
    stats = {}
    for row in cur.fetchall():
        stats[row["Name"]] = {
            "championships": row["Championships"],
            "wins": row["Wins"],
            "podiums": row["Podiums"],
            "poles": row["Poles"],
            "points": row["Points"],
            "starts": row["Starts"],
            "entries": row["Entries"],
        }
    
    conn.close()
    return stats


def fetch_constructor_stats() -> dict[str, dict]:
    """Fetch constructor statistics from the database."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    cur.execute("""
        SELECT ConstructorName, Championships, Wins, Podiums, Poles, Points, Starts, Entries
        FROM Constructors
        WHERE Championships > 0
        ORDER BY ConstructorName
    """)
    
    stats = {}
    for row in cur.fetchall():
        stats[row["ConstructorName"]] = {
            "championships": row["Championships"],
            "wins": row["Wins"],
            "podiums": row["Podiums"],
            "poles": row["Poles"],
            "points": row["Points"],
            "starts": row["Starts"],
            "entries": row["Entries"],
        }
    
    conn.close()
    return stats


def generate_manifest(folder_name: str, category: str, output_json: str, stats: dict[str, dict] | None = None) -> None:
    folder = ROOT / folder_name
    manifest = []

    for image_path in source_images(folder):
        with Image.open(image_path) as image:
            fragments = []
            base_stem = file_slug(image_path)
            for suffix, box in quarter_boxes(*image.size):
                fragment_name = f"{base_stem}-{suffix}.webp"
                fragment_path = folder / fragment_name
                image.crop(box).save(fragment_path, format="WEBP", quality=80, method=6)
                fragments.append(f"{folder_name}/{fragment_name}")

        name = display_name_from_file(image_path)
        entry = {
            "name": name,
            "category": category,
            "fragments": fragments,
        }
        
        # Add rarityScore if stats are provided
        if stats and name in stats:
            stat = stats[name]
            rarity = calculate_rarity_score(
                stat["championships"],
                stat["wins"],
                stat["podiums"],
                stat["poles"],
                stat["points"],
                stat["starts"],
                stat["entries"],
            )
            entry["rarityScore"] = rarity
        
        manifest.append(entry)

    (ROOT / output_json).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder_name}: generated {len(manifest)} entries")


def main() -> None:
    driver_stats = fetch_driver_stats()
    constructor_stats = fetch_constructor_stats()
    
    # Rebuild manifests from existing fragments and add rarityScore
    rebuild_and_enrich_manifest("drivers", "World Champions", "drivers.json", driver_stats)
    rebuild_and_enrich_manifest("constructors", "Constructors' Champions", "constructors.json", constructor_stats)


def rebuild_and_enrich_manifest(folder_name: str, category: str, output_json: str, stats: dict[str, dict]) -> None:
    """Rebuild manifest from fragments and add rarityScore from stats."""
    folder = ROOT / folder_name
    suffixes = ["top-left", "top-right", "bottom-left", "bottom-right"]
    grouped: dict[str, dict[str, Path]] = {}

    # Create case-insensitive lookup for stats
    stats_lower = {k.lower(): v for k, v in stats.items()}

    for path in sorted(folder.glob("*.webp")):
        stem = path.stem
        for suffix in suffixes:
            token = f"-{suffix}"
            if stem.endswith(token):
                base = stem[: -len(token)]
                grouped.setdefault(base, {})[suffix] = path
                break

    manifest = []
    for base, parts in grouped.items():
        if any(suffix not in parts for suffix in suffixes):
            continue
        display_name = base.replace("_", " ").replace("-", " ").strip()
        slug = text_slug(display_name)
        fragments = []
        for suffix in suffixes:
            old_path = parts[suffix]
            new_name = f"{slug}-{suffix}.webp"
            new_path = folder / new_name
            if old_path != new_path:
                old_path.replace(new_path)
            fragments.append(f"https://mclarenmp4-22.github.io/{folder_name}/{new_name}")
        
        entry = {
            "name": re.sub(r"\s+", " ", display_name).strip(),
            "category": category,
            "searchKeywords": re.sub(r"\s+", " ", display_name).strip(),
            "fragments": fragments,
        }
        
        # Add rarityScore if stats are provided
        # Use case-insensitive lookup
        name_lower = entry["name"].lower()
        if name_lower in stats_lower:
            stat = stats_lower[name_lower]
            rarity = calculate_rarity_score(
                stat["championships"],
                stat["wins"],
                stat["podiums"],
                stat["poles"],
                stat["points"],
                stat["starts"],
                stat["entries"],
            )
            entry["rarityScore"] = rarity
        
        manifest.append(entry)

    manifest.sort(key=lambda item: item["name"])
    (ROOT / output_json).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder_name}: rebuilt {len(manifest)} entries")


def rewrite_manifest_with_safe_filenames(folder_name: str, output_json: str) -> None:
    folder = ROOT / folder_name
    manifest_path = ROOT / output_json
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    updated = []

    for entry in manifest:
        old_paths = [ROOT / fragment for fragment in entry["fragments"]]
        new_fragments = []
        base = text_slug(entry["name"])
        suffixes = ["top-left", "top-right", "bottom-left", "bottom-right"]
        for old_path, suffix in zip(old_paths, suffixes):
            new_name = f"{base}-{suffix}.webp"
            new_path = folder / new_name
            if old_path != new_path and old_path.exists():
                old_path.replace(new_path)
            new_fragments.append(f"{folder_name}/{new_name}")
        updated.append(
            {
                "name": entry["name"],
                "category": entry["category"],
                "fragments": new_fragments,
            }
        )

    manifest_path.write_text(json.dumps(updated, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder_name}: rewrote {len(updated)} entries")



def rebuild_manifest_from_fragments(folder_name: str, category: str, output_json: str) -> None:
    folder = ROOT / folder_name
    suffixes = ["top-left", "top-right", "bottom-left", "bottom-right"]
    grouped: dict[str, dict[str, Path]] = {}

    for path in sorted(folder.glob("*.webp")):
        stem = path.stem
        for suffix in suffixes:
            token = f"-{suffix}"
            if stem.endswith(token):
                base = stem[: -len(token)]
                grouped.setdefault(base, {})[suffix] = path
                break

    manifest = []
    for base, parts in grouped.items():
        if any(suffix not in parts for suffix in suffixes):
            continue
        display_name = base.replace("_", " ").replace("-", " ").strip()
        slug = text_slug(display_name)
        fragments = []
        for suffix in suffixes:
            old_path = parts[suffix]
            new_name = f"{slug}-{suffix}.webp"
            new_path = folder / new_name
            if old_path != new_path:
                old_path.replace(new_path)
            fragments.append(f"https://mclarenmp4-22.github.io/{folder_name}/{new_name}")
        manifest.append(
            {
                "name": re.sub(r"\s+", " ", display_name).strip(),
                "category": category,
                "searchKeywords": re.sub(r"\s+", " ", display_name).strip(),
                "fragments": fragments, 
            }
        )

    manifest.sort(key=lambda item: item["name"])
    (ROOT / output_json).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder_name}: rebuilt {len(manifest)} entries")


if __name__ == "__main__":
    main()
