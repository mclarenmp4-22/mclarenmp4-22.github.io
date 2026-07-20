import os
import re
import unicodedata
from PIL import Image

UNCROPPED_DIR = "drivers_uncropped"
OUTPUT_DIR = "drivers_undivided"
OUTPUT_WIDTH = 1000
OUTPUT_HEIGHT = 600

def sanitize(name: str) -> str:
    name = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode('ascii')
    name = name.lower().strip()
    return re.sub(r"[^a-z0-9]+", "-", name).strip("-")

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
    return img.resize((OUTPUT_WIDTH, OUTPUT_HEIGHT), Image.Resampling.LANCZOS)

def process():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    files = os.listdir(UNCROPPED_DIR)
    print(f"Found {len(files)} files in {UNCROPPED_DIR}")
    
    processed_count = 0
    for filename in files:
        # Expected pattern: drivers_uncropped_Driver_Name.ext
        if not filename.startswith("drivers_uncropped_"):
            continue
            
        base, ext = os.path.splitext(filename)
        driver_part = base[len("drivers_uncropped_"):]
        driver_name = driver_part.replace("_", " ")
        driver_slug = sanitize(driver_name)
        
        # Determine next index
        existing = [f for f in os.listdir(OUTPUT_DIR) if f.startswith(driver_slug)]
        indices = []
        for f in existing:
            m = re.match(rf"^{re.escape(driver_slug)}_(\d+)\.webp$", f)
            if m:
                indices.append(int(m.group(1)))
        next_idx = max(indices) + 1 if indices else 1
        
        src_path = os.path.join(UNCROPPED_DIR, filename)
        dest_filename = f"{driver_slug}_{next_idx}.webp"
        dest_path = os.path.join(OUTPUT_DIR, dest_filename)
        
        try:
            with Image.open(src_path) as img:
                img = img.convert("RGB")
                cropped = crop_to_16x9(img)
                cropped.save(dest_path, format="WEBP", quality=80)
                print(f"[OK] Cropped {filename} -> {dest_filename}")
                processed_count += 1
        except Exception as e:
            print(f"[ERROR] Error processing {filename}: {e}")
            
    print(f"Done! Processed {processed_count} images.")

if __name__ == "__main__":
    process()
