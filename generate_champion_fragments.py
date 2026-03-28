import json
import re
from pathlib import Path

from PIL import Image


ROOT = Path(__file__).resolve().parent


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


def generate_manifest(folder_name: str, category: str, output_json: str) -> None:
    folder = ROOT / folder_name
    manifest = []

    for image_path in source_images(folder):
        with Image.open(image_path) as image:
            fragments = []
            base_stem = clean_stem(image_path)
            for suffix, box in quarter_boxes(*image.size):
                fragment_name = f"{base_stem}-{suffix}.webp"
                fragment_path = folder / fragment_name
                image.crop(box).save(fragment_path, format="WEBP", quality=80, method=6)
                fragments.append(f"{folder_name}/{fragment_name}")

        manifest.append(
            {
                "name": display_name_from_file(image_path),
                "category": category,
                "fragments": fragments,
            }
        )

    (ROOT / output_json).write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"{folder_name}: generated {len(manifest)} entries")


def main() -> None:
    generate_manifest("drivers", "World Champions", "drivers.json")
    generate_manifest("constructors", "Constructors' Champions", "constructors.json")


if __name__ == "__main__":
    main()
