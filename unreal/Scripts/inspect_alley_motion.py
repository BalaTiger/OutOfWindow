"""Report temporal image changes in the fixed alley view (Pillow only).

Usage: python unreal/Scripts/inspect_alley_motion.py ".runtime/ue-validation/motion"
Use clear noon captures from one settled run. Results are diagnostics: inspect
the sequence as well, since temporal lighting/noise can also change pixels.
"""
import argparse
import glob
import json
from pathlib import Path
from statistics import mean, median

from PIL import Image, ImageChops, ImageDraw, ImageStat


REGIONS = {
    "foliage": (448, 630, 527, 819),
    "awning_front_rim": (728, 653, 897, 700),
    "awning_right_rim": (979, 640, 1148, 684),
    "plaster_control": (660, 190, 750, 280),
    "upper_sky": (210, 0, 550, 145),
}
CLOTH_EDGES = {
    "awning_front_rim": (752, 650, 873, 705),
    "awning_right_rim": (1000, 640, 1130, 690),
}


def region_box(box, size):
    return tuple(round(value * size[index % 2] / (1280, 820)[index % 2])
                 for index, value in enumerate(box))


def measure(paths):
    extrema = {}
    contours = {name: [] for name in CLOTH_EDGES}
    size = None
    for path in paths:
        with Image.open(path) as image:
            if size is None:
                size = image.size
            if image.size != size:
                raise ValueError(f"Frame dimensions differ: {path}")
            gray = image.convert("L")
            for name, box in REGIONS.items():
                crop = gray.crop(region_box(box, size))
                low, high = extrema.get(name, (crop, crop))
                extrema[name] = (ImageChops.darker(low, crop), ImageChops.lighter(high, crop))
            rgb = image.convert("RGB")
            for name, box in CLOTH_EDGES.items():
                scaled = region_box(box, size)
                crop = rgb.crop(scaled)
                pixels = crop.load()
                edge = []
                for x in range(crop.width):
                    pink = [y for y in range(crop.height)
                            if (p := pixels[x, y])[0] > 100 and p[0] - p[1] > 20 and p[0] - p[2] > 20]
                    edge.append(scaled[1] + max(pink) if pink else None)
                contours[name].append(edge)
    regions = {}
    for name, (low, high) in extrema.items():
        delta = ImageChops.subtract(high, low)
        histogram = delta.histogram()
        pixels = delta.width * delta.height
        regions[name] = {
            "mean_range_255": round(ImageStat.Stat(delta).mean[0], 3),
            "changed_above_12_percent": round(100 * sum(histogram[13:]) / pixels, 3),
        }
    silhouettes = {}
    for name, curves in contours.items():
        # Keep identical columns across frames so entering/leaving the mask does
        # not move the reported average. Pink threshold is for clear daytime.
        columns = [x for x in range(len(curves[0])) if all(curve[x] is not None for curve in curves)]
        positions = [mean(curve[x] for x in columns) for curve in curves] if columns else []
        ranges = [max(curve[x] for curve in curves) - min(curve[x] for curve in curves) for x in columns]
        silhouettes[name] = {
            "tracked_columns": len(columns),
            "mean_bottom_edge_y_px": [round(value, 3) for value in positions],
            "mean_edge_range_px": round(max(positions) - min(positions), 3) if positions else None,
            "median_column_range_px": median(ranges) if ranges else None,
        }
    return {"frames": len(paths), "size": size, "regions": regions, "cloth_silhouettes": silhouettes,
            "note": "Luminance range includes lighting/noise. Cloth tracks the pink lower silhouette in clear daylight; inspect the edge trajectory and crops, without treating either metric as proof of motion."}


def contact_sheet(paths, output):
    indices = [0, len(paths) // 2, len(paths) - 1]
    frames = []
    for index in indices:
        with Image.open(paths[index]) as image:
            frames.append(image.convert("RGB"))
    rows = []
    for name, box in REGIONS.items():
        crops = [frame.crop(region_box(box, frame.size)) for frame in frames]
        scale = min(2, 380 / crops[0].width)
        width, height = round(crops[0].width * scale), round(crops[0].height * scale)
        row = Image.new("RGB", (1200, height + 36), "#eeeeee")
        draw = ImageDraw.Draw(row)
        for column, (crop, index) in enumerate(zip(crops, indices)):
            draw.text((column * 400 + 10, 8), f"{name} | frame {index + 1}", fill="black")
            row.paste(crop.resize((width, height), Image.Resampling.NEAREST), (column * 400 + 10, 28))
        rows.append(row)
    sheet = Image.new("RGB", (1200, sum(row.height for row in rows)), "white")
    top = 0
    for row in rows:
        sheet.paste(row, (0, top))
        top += row.height
    sheet.save(output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sequence", help="Sequence folder, filename prefix, or quoted PNG glob pattern")
    parser.add_argument("--output", type=Path, required=True, help="JSON report; contact sheet uses the same stem plus -crops.jpg")
    args = parser.parse_args()
    source = Path(args.sequence)
    pattern = str(source / "*.png") if source.is_dir() else args.sequence if glob.has_magic(args.sequence) else args.sequence + "*.png"
    paths = sorted(glob.glob(pattern))
    if len(paths) < 2:
        parser.error("At least two frames are required")
    report = measure(paths)
    sheet_path = args.output.with_name(args.output.stem + "-crops.jpg")
    contact_sheet(paths, sheet_path)
    report["contact_sheet"] = str(sheet_path.resolve())
    report = json.dumps(report, indent=2)
    args.output.write_text(report + "\n", encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
