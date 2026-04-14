import os
import re
import unicodedata
import sqlite3
from pathlib import Path

DB_PATH = r"c:\Users\trues\OneDrive\Desktop\Advaith\F1 Results database, upgraded\sessionresults.db"

def old_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower().strip()).strip("-")

def new_slug(name: str) -> str:
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")

def migrate_undivided(folder_path: str, table: str, name_col: str):
    folder = Path(folder_path)
    if not folder.exists():
        return
    
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"SELECT {name_col} FROM {table}")
    names = [row[0] for row in cur.fetchall()]
    conn.close()
    
    # Map old slugs to new slugs
    mapping = {}
    for name in names:
        old = old_slug(name)
        new = new_slug(name)
        if old != new:
            mapping[old] = new
    
    print(f"Found {len(mapping)} possible renames for {table}")

    for f in folder.glob("*.webp"):
        stem = f.stem
        base = stem
        suffix = ""
        if "_" in stem:
            base, suffix = stem.rsplit("_", 1)
        
        if base in mapping:
            new_base = mapping[base]
            new_name = f"{new_base}_{suffix}.webp" if suffix else f"{new_base}.webp"
            target = folder / new_name
            print(f"Migrating {f.name} -> {new_name}")
            if target.exists():
                f.unlink()
            else:
                f.rename(target)

if __name__ == "__main__":
    migrate_undivided(r"c:\Users\trues\OneDrive\Desktop\Advaith\vault_images\drivers_undivided", "Drivers", "Name")
    migrate_undivided(r"c:\Users\trues\OneDrive\Desktop\Advaith\vault_images\constructors_undivided", "Constructors", "ConstructorName")
