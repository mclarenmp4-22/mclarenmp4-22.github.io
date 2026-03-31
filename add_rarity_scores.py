"""Add rarityScore to existing JSON files from database statistics."""

import json
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(r"sessionresults.db")


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


def add_rarity_scores_to_json(json_file: str, stats: dict[str, dict], name_key: str = "name") -> int:
    """Add rarityScore to entries in a JSON file based on stats."""
    json_path = ROOT / json_file
    manifest = json.loads(json_path.read_text(encoding="utf-8"))
    
    count = 0
    for entry in manifest:
        name = entry[name_key]
        if name in stats:
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
            count += 1
    
    json_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return count


def main() -> None:
    print("Fetching statistics from database...")
    driver_stats = fetch_driver_stats()
    constructor_stats = fetch_constructor_stats()
    
    print(f"Found {len(driver_stats)} drivers with stats")
    print(f"Found {len(constructor_stats)} constructors with stats")
    
    print("\nAdding rarityScore to drivers.json...")
    drivers_updated = add_rarity_scores_to_json("drivers.json", driver_stats)
    print(f"Updated {drivers_updated} drivers")
    
    print("\nAdding rarityScore to constructors.json...")
    constructors_updated = add_rarity_scores_to_json("constructors.json", constructor_stats, "name")
    print(f"Updated {constructors_updated} constructors")


if __name__ == "__main__":
    main()
