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


def generate_manifest(folder_name: str, category: str, output_json: str) -> None:
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
            fragments.append(f"{folder_name}/{new_name}")
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
