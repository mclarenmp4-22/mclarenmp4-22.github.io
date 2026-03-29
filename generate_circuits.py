import json
import re
import sqlite3
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).resolve().parent
DB_PATH = Path(r"c:\Users\trues\OneDrive\Desktop\Advaith\F1 Results database, upgraded\sessionresults.db")
OUTPUT_DIR = ROOT / "circuits"
OUTPUT_JSON = ROOT / "circuits.json"
TARGET_SIZE = (1000, 600)
BACKGROUND = "#111111"
DEFAULT_STROKE = "#FFFFFF"
WEBP_QUALITY = 76


def slugify(value: str) -> str:
    value = value.lower().strip()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-")


def parse_viewbox(root: ET.Element) -> tuple[float, float, float, float]:
    view_box = root.attrib.get("viewBox")
    if view_box:
        parts = [float(part) for part in view_box.replace(",", " ").split()]
        if len(parts) == 4:
            return tuple(parts)  # type: ignore[return-value]
    width = float(root.attrib.get("width", TARGET_SIZE[0]))
    height = float(root.attrib.get("height", TARGET_SIZE[1]))
    return 0.0, 0.0, width, height


def parse_style(style: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for part in style.split(";"):
        if ":" not in part:
            continue
        key, value = part.split(":", 1)
        parsed[key.strip()] = value.strip()
    return parsed


def parse_points(points: str) -> list[tuple[float, float]]:
    coords = [float(piece) for piece in points.replace(",", " ").split()]
    return [(coords[i], coords[i + 1]) for i in range(0, len(coords), 2)]


def get_color(elem: ET.Element, parent_style: dict[str, str], attr_name: str, fallback: str) -> str:
    inline_style = parse_style(elem.attrib.get("style", ""))
    return elem.attrib.get(attr_name) or inline_style.get(attr_name) or parent_style.get(attr_name) or fallback


def get_stroke_width(elem: ET.Element, parent_style: dict[str, str]) -> int:
    inline_style = parse_style(elem.attrib.get("style", ""))
    value = elem.attrib.get("stroke-width") or inline_style.get("stroke-width") or parent_style.get("stroke-width") or "4"
    try:
        return max(1, int(round(float(value))))
    except ValueError:
        return 4


def render_svg(svg_text: str) -> Image.Image:
    root = ET.fromstring(svg_text)
    view_x, view_y, view_w, view_h = parse_viewbox(root)
    target_w, target_h = TARGET_SIZE
    scale = min(target_w / view_w, target_h / view_h)
    offset_x = (target_w - view_w * scale) / 2
    offset_y = (target_h - view_h * scale) / 2

    image = Image.new("RGB", TARGET_SIZE, BACKGROUND)
    draw = ImageDraw.Draw(image)

    def project(point: tuple[float, float]) -> tuple[float, float]:
        x, y = point
        return ((x - view_x) * scale + offset_x, (y - view_y) * scale + offset_y)

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag not in {"polyline", "polygon"}:
            continue

        parent = elem.getparent() if hasattr(elem, "getparent") else None
        parent_style = parse_style(parent.attrib.get("style", "")) if parent is not None else {}
        if not parent_style:
            for group in root.findall(".//{http://www.w3.org/2000/svg}g") + root.findall(".//g"):
                if elem in list(group):
                    parent_style = parse_style(group.attrib.get("style", ""))
                    parent_style.update({k: v for k, v in group.attrib.items() if k in {"fill", "stroke", "stroke-width"}})
                    break

        points = parse_points(elem.attrib.get("points", ""))
        if len(points) < 2:
            continue

        stroke = get_color(elem, parent_style, "stroke", DEFAULT_STROKE)
        fill = get_color(elem, parent_style, "fill", "none")
        width = max(1, int(round(get_stroke_width(elem, parent_style) * scale)))
        projected = [project(point) for point in points]

        if tag == "polygon" and fill != "none":
            draw.polygon(projected, fill=fill)
        if tag == "polygon":
            projected = projected + [projected[0]]
        draw.line(projected, fill=stroke, width=width, joint="curve")

    return image


def fragment_regions(grand_prix_count: int) -> list[tuple[str, tuple[int, int, int, int]]]:
    full_w, full_h = TARGET_SIZE
    if grand_prix_count < 5:
        return [("full", (0, 0, full_w, full_h))]
    half_w = full_w // 2
    if grand_prix_count > 20:
        half_h = full_h // 2
        return [
            ("top-left", (0, 0, half_w, half_h)),
            ("top-right", (half_w, 0, full_w, half_h)),
            ("bottom-left", (0, half_h, half_w, full_h)),
            ("bottom-right", (half_w, half_h, full_w, full_h)),
        ]
    return [
        ("left", (0, 0, half_w, full_h)),
        ("right", (half_w, 0, full_w, full_h)),
    ]


def build_name(first_gp: str, last_gp: str) -> str:
    first_year = first_gp[:4]
    last_year = last_gp[:4]
    if first_year == last_year:
        return first_year
    return f"{first_year}-{last_year}"


def main() -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        """
        WITH LatestLocationName AS (
            SELECT cl.Latitude, cl.Longitude, g.CircuitName
            FROM CircuitLayouts cl
            JOIN GrandsPrix g ON g.ID = cl.LastGrandPrixID
            WHERE cl.LastGrandPrixID = (
                SELECT MAX(cl2.LastGrandPrixID)
                FROM CircuitLayouts cl2
                WHERE cl2.Latitude = cl.Latitude
                  AND cl2.Longitude = cl.Longitude
            )
        )
        SELECT
            cl.ID,
            cl.FirstGrandPrix,
            cl.LastGrandPrix,
            cl.GrandPrixCount,
            cl.SVG,
            lln.CircuitName
        FROM CircuitLayouts cl
        JOIN LatestLocationName lln
          ON lln.Latitude = cl.Latitude
         AND lln.Longitude = cl.Longitude
        ORDER BY substr(cl.FirstGrandPrix, 1, 4), lln.CircuitName, cl.ID
        """
    )
    rows = cur.fetchall()
    conn.close()

    manifest = []
    for row in rows:
        svg_text = row["SVG"]
        name = build_name(row["FirstGrandPrix"], row["LastGrandPrix"])
        circuit_name = row["CircuitName"]
        base_slug = f"{name}-{slugify(circuit_name)}-{row['ID']}"
        fragments = []
        full_image = render_svg(svg_text)

        for fragment_name, crop_box in fragment_regions(row["GrandPrixCount"]):
            image = full_image.crop(crop_box)
            filename = f"{base_slug}-{fragment_name}.webp"
            image.save(OUTPUT_DIR / filename, format="WEBP", quality=WEBP_QUALITY, method=6)
            fragments.append(f"circuits/{filename}")

        manifest.append(
            {
                "name": name,
                "category": circuit_name,
                "searchKeywords": f"{circuit_name} ({name})",
                "fragments": fragments,
            }
        )

    OUTPUT_JSON.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Generated {len(manifest)} circuit entries")


if __name__ == "__main__":
    main()
