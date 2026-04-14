import os
import re
import unicodedata
from pathlib import Path

def clean_slug(text: str) -> str:
    text = unicodedata.normalize('NFKD', text).encode('ascii', 'ignore').decode('ascii')
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")

def fix_undivided(folder_path: str):
    folder = Path(folder_path)
    if not folder.exists():
        return
    
    for f in folder.glob("*.webp"):
        stem = f.stem
        # Separate base from numeric suffix
        if "_" in stem:
            base, suffix = stem.rsplit("_", 1)
            new_base = clean_slug(base)
            new_name = f"{new_base}_{suffix}.webp"
        else:
            new_name = f"{clean_slug(stem)}.webp"
        
        if f.name != new_name:
            target = folder / new_name
            print(f"Renaming {f.name} -> {new_name}")
            if target.exists():
                f.unlink() # Delete duplicate
            else:
                f.rename(target)

if __name__ == "__main__":
    fix_undivided(r"c:\Users\trues\OneDrive\Desktop\Advaith\vault_images\drivers_undivided")
    fix_undivided(r"c:\Users\trues\OneDrive\Desktop\Advaith\vault_images\constructors_undivided")
