"""Compare rain-cloud captures using an eroded, depth-derived sky mask.

    python cloud-ab-report.py .runtime/ue-cloud-ab [baseline exposure-minus1 ...]

Only JSON files with an existing capture and a valid skyMask are cases. Metrics
use the common eroded sky area across all cases, so roof/window boundary samples
and changing measurement footprints cannot masquerade as cloud contrast. Output
tones are preserved; no image is normalized or auto-contrasted. PIL + stdlib only.
Use --allow-shape-change for a deliberate cloud-material/layout comparison;
weather, density and cloud rendering components must still match. Deliberate
shadow/lighting changes also require --allow-lighting-change. Missing colour,
AO and multiple-scattering audit values leave their consistency unverified.
"""

import argparse
import json
import math
import statistics
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont


def decode_mask(state):
    width, height = state.get("skyMaskWidth", 0), state.get("skyMaskHeight", 0)
    encoded = state.get("skyMask", "")
    if width <= 0 or height <= 0 or not encoded:
        raise ValueError("missing depth-derived skyMask")
    raw = bytes.fromhex(encoded)
    if len(raw) != width * height:
        raise ValueError("skyMask byte count does not match its dimensions")
    return Image.frombytes("L", (width, height), raw).point(lambda value: 255 if value == 255 else 0)


def erode_mask(mask, cells):
    # The zero border is deliberate: PIL's own edge extension would retain an
    # all-sky pixel touching the render edge without a complete neighbourhood.
    result = mask
    for _ in range(cells):
        padded = Image.new("L", (result.width + 2, result.height + 2), 0)
        padded.paste(result, (1, 1))
        result = padded.filter(ImageFilter.MinFilter(3)).crop((1, 1, result.width + 1, result.height + 1))
    return result


def load_case(path, cells):
    with path.open(encoding="utf-8-sig") as handle:
        state = json.load(handle)
    if not isinstance(state, dict) or not state.get("capture"):
        raise ValueError("not a capture state")
    capture = Path(state["capture"])
    if not capture.is_file():
        # Adjacent captures keep reports usable when a diagnostic folder moves.
        capture = path.with_suffix(".png")
    if not capture.is_file():
        raise ValueError("capture does not exist")
    image = Image.open(capture).convert("RGB")
    raw_mask = decode_mask(state)
    return {"name": path.stem, "statePath": path, "capturePath": capture,
            "state": state, "image": image, "rawMask": raw_mask,
            "erodedMask": erode_mask(raw_mask, cells)}


def percentile(ordered, fraction):
    position = (len(ordered) - 1) * fraction
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def pixel_data(image):
    flattened = getattr(image, "get_flattened_data", None)
    return flattened() if flattened is not None else image.getdata()


def tonal_stats(image, mask):
    samples = [rgb for rgb, sky in zip(pixel_data(image), pixel_data(mask)) if sky == 255]
    if not samples:
        raise ValueError("eroded common mask selects no sky pixels")
    luminance = [0.2126 * rgb[0] + 0.7152 * rgb[1] + 0.0722 * rgb[2] for rgb in samples]
    ordered = sorted(luminance)
    mean = statistics.fmean(luminance)
    deviation = statistics.pstdev(luminance)
    p5, p95 = percentile(ordered, .05), percentile(ordered, .95)
    return {
        "pixels": len(samples),
        "meanRGB": [statistics.fmean(rgb[channel] for rgb in samples) for channel in range(3)],
        "luminanceMean": mean,
        "luminanceStd": deviation,
        "coefficientOfVariation": deviation / mean if mean else 0,
        "p1": percentile(ordered, .01), "p5": p5,
        "p50": percentile(ordered, .5), "p95": p95,
        "p99": percentile(ordered, .99),
        "p95MinusP5": p95 - p5,
        "p5P95MichelsonContrast": (p95 - p5) / (p95 + p5) if p95 + p5 else 0,
        "fractionLuminanceGe230": sum(value >= 230 for value in luminance) / len(samples),
        "fractionLuminanceGe245": sum(value >= 245 for value in luminance) / len(samples),
        "fractionLuminanceGe250": sum(value >= 250 for value in luminance) / len(samples),
        "fractionAnyChannelGe250": sum(max(rgb) >= 250 for rgb in samples) / len(samples),
        "fractionAllChannelsGe250": sum(min(rgb) >= 250 for rgb in samples) / len(samples),
        "fractionAllChannelsEq255": sum(min(rgb) == 255 for rgb in samples) / len(samples),
    }


def padded_bbox(box, size, padding):
    x0, y0, x1, y1 = box
    return (max(0, x0 - padding), max(0, y0 - padding),
            min(size[0], x1 + padding), min(size[1], y1 + padding))


def fit_crop(crop, size):
    scale = min(size[0] / crop.width, size[1] / crop.height)
    scaled = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.NEAREST)
    panel = Image.new("RGB", size, (17, 21, 28))
    panel.paste(scaled, ((size[0] - scaled.width) // 2, (size[1] - scaled.height) // 2))
    return panel


def read_font(size):
    for name in ("C:/Windows/Fonts/consola.ttf", "DejaVuSansMono.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            pass
    return ImageFont.load_default()


def number(value, decimals=3):
    return f"{value:.{decimals}f}" if isinstance(value, (float, int)) else "?"


def diagnostic_cvars(state):
    return {key: value for key, value in state.items() if key.startswith(("r.", "oow.", "ShowFlag."))}


def additional_lighting_audit(parameters, reference_parameters):
    groups = {"color": [], "ambientOcclusion": [], "multipleScattering": []}
    for name in sorted(set(parameters) | set(reference_parameters)):
        lower = name.lower()
        if "albedo" in lower or "color" in lower or "colour" in lower:
            groups["color"].append(name)
        if "ambientocclusion" in lower or "ambient_occlusion" in lower or lower.startswith("ao_") or "_ao" in lower:
            groups["ambientOcclusion"].append(name)
        if "multiscatter" in lower or "multi_scatter" in lower:
            groups["multipleScattering"].append(name)
    coverage = {}
    differences = []
    for group, fields in groups.items():
        comparable = [name for name in fields if parameters.get(name) is not None and reference_parameters.get(name) is not None]
        missing = [name for name in fields if name not in comparable]
        changed = []
        for name in comparable:
            current, baseline = parameters[name], reference_parameters[name]
            if isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
                different = abs(current - baseline) > .001
            elif isinstance(current, list) and isinstance(baseline, list) and len(current) == len(baseline):
                different = any(abs(a - b) > .001 for a, b in zip(current, baseline))
            else:
                different = current != baseline
            if different:
                changed.append(name)
                differences.append({"field": name, "case": current, "baseline": baseline})
        coverage[group] = {
            "status": "different" if changed else "unknown" if not comparable or missing else "consistent for audited fields",
            "auditedFields": comparable, "missingFromOneAudit": missing, "changedFields": changed,
            "note": "Only supplied audit values are checked; absent material properties are not inferred.",
        }
    return coverage, differences


def cloud_state_comparison(state, reference, allow_shape_change=False, allow_lighting_change=False):
    differences = []
    shape_differences = []
    lighting_differences = []
    parameters, reference_parameters = state.get("cloudParameters") or {}, reference.get("cloudParameters") or {}
    checks = [
        ("cloudiness", state.get("cloudiness"), reference.get("cloudiness"), .005),
        ("Cloud_GlobalCoverage", parameters.get("Cloud_GlobalCoverage"), reference_parameters.get("Cloud_GlobalCoverage"), .005),
        ("StormClouds", parameters.get("StormClouds"), reference_parameters.get("StormClouds"), .005),
        ("Cloud_GlobalDensity", parameters.get("Cloud_GlobalDensity"), reference_parameters.get("Cloud_GlobalDensity"), .001),
        ("cloudLayerBottomKm", state.get("cloudLayerBottomKm"), reference.get("cloudLayerBottomKm"), .01),
        ("cloudLayerHeightKm", state.get("cloudLayerHeightKm"), reference.get("cloudLayerHeightKm"), .01),
    ]
    for name, current, baseline, tolerance in checks:
        if not isinstance(current, (int, float)) or not isinstance(baseline, (int, float)):
            differences.append({"field": name, "case": current, "baseline": baseline, "reason": "missing numeric cloud state"})
        elif abs(current - baseline) > tolerance:
            differences.append({"field": name, "case": current, "baseline": baseline,
                                "difference": current - baseline, "tolerance": tolerance})
    for name in ("Layout_CloudGlobalScale", "OOW_CellSpacingKm", "OOW_StormOffsetKm",
                 "OOW_DetailStrength", "OOW_DetailScaleKm", "OOW_DetailDensityScale"):
        current, baseline = parameters.get(name), reference_parameters.get(name)
        if isinstance(current, (int, float)) and isinstance(baseline, (int, float)):
            different = abs(current - baseline) > .001
        elif isinstance(current, list) and isinstance(baseline, list) and len(current) == len(baseline):
            different = any(abs(a - b) > .001 for a, b in zip(current, baseline))
        else:
            different = current != baseline
        if different:
            shape_differences.append({"field": name, "case": current, "baseline": baseline})
    for name in ("cloudMaterial", "oow.CloudLayoutScale", "oow.StormOffsetXKm", "oow.StormOffsetYKm", "oow.StormCellSpacingKm"):
        if state.get(name) != reference.get(name):
            shape_differences.append({"field": name, "case": state.get(name), "baseline": reference.get(name)})
    for name in ("scene", "actualWeather", "weatherMode", "quality", "cloudShadowsEnabled",
                 "r.VolumetricCloud", "r.VolumetricRenderTarget", "r.VolumetricRenderTarget.Mode",
                 "r.VolumetricCloud.DistanceToSampleMaxCount", "ShowFlag.Cloud"):
        if state.get(name) != reference.get(name):
            differences.append({"field": name, "case": state.get(name), "baseline": reference.get(name)})
    if abs(state.get("hour", 0) - reference.get("hour", 0)) > .02:
        differences.append({"field": "hour", "case": state.get("hour"), "baseline": reference.get("hour"), "tolerance": .02})
    for name, tolerance in (("cloudShadowViewSampleScale", .001), ("cloudShadowTracingDistanceKm", .01)):
        current, baseline = state.get(name), reference.get(name)
        if current is None and baseline is None:
            continue  # Older reports do not audit these components.
        if not isinstance(current, (int, float)) or not isinstance(baseline, (int, float)):
            lighting_differences.append({"field": name, "case": current, "baseline": baseline,
                                         "reason": "missing numeric shadow state in one audit"})
        elif abs(current - baseline) > tolerance:
            lighting_differences.append({"field": name, "case": current, "baseline": baseline,
                                         "difference": current - baseline, "tolerance": tolerance})
    lighting_coverage, audited_lighting_differences = additional_lighting_audit(parameters, reference_parameters)
    lighting_differences.extend(audited_lighting_differences)
    if shape_differences and not allow_shape_change:
        differences.extend(shape_differences)
    if lighting_differences and not allow_lighting_change:
        differences.extend(lighting_differences)
    if differences:
        status = "rejected"
    elif shape_differences and lighting_differences:
        status = "shape and lighting changed intentionally"
    elif shape_differences:
        status = "shape changed intentionally"
    elif lighting_differences:
        status = "lighting changed intentionally"
    else:
        status = "accepted"
    return {"status": status,
            "purpose": "cloud-state validity for weather/lighting isolation; shape and lighting differences require their separate explicit flags",
            "reasons": differences,
            "intentionalShapeDifferences": shape_differences if allow_shape_change else [],
            "intentionalLightingDifferences": lighting_differences if allow_lighting_change else [],
            "additionalLightingAudit": lighting_coverage,
            "shadowAudit": {name: "unknown: neither audit provides this field" if state.get(name) is None and reference.get(name) is None
                else "unknown: one audit does not provide this field" if state.get(name) is None or reference.get(name) is None
                else "provided in both audits"
                for name in ("cloudShadowViewSampleScale", "cloudShadowTracingDistanceKm")}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("cases", nargs="*", help="JSON stems in desired display order; otherwise discover all captures")
    parser.add_argument("--erode-cells", type=int, default=1)
    parser.add_argument("--padding", type=int, default=16)
    parser.add_argument("--columns", type=int, default=2)
    parser.add_argument("--out-prefix", default="cloud-ab")
    parser.add_argument("--allow-shape-change", action="store_true", help="Allow intended cloud material/layout/spacing/offset changes while checking weather, density and rendering components")
    parser.add_argument("--allow-lighting-change", action="store_true", help="Allow explicitly intended shadow or audited color/AO/multiple-scattering differences")
    args = parser.parse_args()
    if args.erode_cells < 0 or args.padding < 0 or args.columns < 1:
        parser.error("erosion/padding must be nonnegative and columns must be positive")
    directory = args.directory.resolve()
    paths = [directory / (name if name.endswith(".json") else name + ".json") for name in args.cases] if args.cases else sorted(directory.glob("*.json"), key=lambda path: (path.stem != "baseline", path.stem))
    cases, skipped = [], []
    for path in paths:
        try:
            cases.append(load_case(path, args.erode_cells))
        except (OSError, ValueError, KeyError) as error:
            if args.cases:
                parser.error(f"{path.name}: {error}")
            skipped.append({"path": str(path), "reason": str(error)})
    if not cases:
        parser.error("no captured cases with usable depth-derived sky masks")
    reference_size = cases[0]["image"].size
    reference_mask_size = cases[0]["rawMask"].size
    if any(case["image"].size != reference_size or case["rawMask"].size != reference_mask_size for case in cases):
        parser.error("all captures and mask grids must have matching dimensions for common-pixel comparison")
    common = cases[0]["erodedMask"].copy()
    for case in cases[1:]:
        common = ImageChops.darker(common, case["erodedMask"])
    if common.getbbox() is None:
        parser.error("eroded masks have no common sky area; inspect masks or reduce --erode-cells")
    full_mask = common.resize(reference_size, Image.Resampling.NEAREST)
    # Show the complete visible-sky opening, including roofline context; measure
    # only its eroded core. Every case receives exactly the same crop coordinates.
    raw_union = cases[0]["rawMask"].copy()
    for case in cases[1:]:
        raw_union = ImageChops.lighter(raw_union, case["rawMask"])
    raw_full = raw_union.resize(reference_size, Image.Resampling.NEAREST)
    crop_bbox = padded_bbox(raw_full.getbbox(), reference_size, args.padding)
    out = directory / args.out_prefix
    full_mask.save(str(out) + "-common-sky-mask.png")
    font, small_font = read_font(19), read_font(15)
    panel_size = (328, 350)
    tile_width, tile_height = panel_size[0] * 2 + 32, panel_size[1] + 144
    columns = min(args.columns, len(cases))
    sheet = Image.new("RGB", (columns * tile_width, math.ceil(len(cases) / columns) * tile_height + 70), (24, 29, 38))
    drawing = ImageDraw.Draw(sheet)
    drawing.text((16, 10), "Rain-cloud A/B: original sky crop | common eroded sky only", fill="white", font=font)
    margin_x = args.erode_cells * reference_size[0] / reference_mask_size[0]
    margin_y = args.erode_cells * reference_size[1] / reference_mask_size[1]
    drawing.text((16, 38), f"Same ROI / original tones / eroded margin about {margin_x:.0f} x {margin_y:.0f} px", fill=(180, 190, 203), font=small_font)
    reference = next((case for case in cases if case["name"] == "baseline"), cases[0])
    reference_stats = tonal_stats(reference["image"], full_mask)
    results = []
    for index, case in enumerate(cases):
        image, state = case["image"], case["state"]
        stats = tonal_stats(image, full_mask)
        own_raw = sum(value == 255 for value in pixel_data(case["rawMask"]))
        own_eroded = sum(value == 255 for value in pixel_data(case["erodedMask"]))
        exposure = state.get("finalViewPostProcess", {})
        comparison = cloud_state_comparison(state, reference["state"], args.allow_shape_change, args.allow_lighting_change)
        original_crop = image.crop(crop_bbox)
        sky_only = Image.composite(image, Image.new("RGB", image.size, (17, 21, 28)), full_mask).crop(crop_bbox)
        prefix = directory / (case["name"] + "-sky")
        original_crop.save(str(prefix) + "-crop.png")
        sky_only.save(str(prefix) + "-only.png")
        full_mask.crop(crop_bbox).save(str(prefix) + "-mask.png")
        tinted = Image.composite(Image.blend(image, Image.new("RGB", image.size, (255, 50, 45)), .4), image, full_mask).crop(crop_bbox)
        tinted.save(str(prefix) + "-overlay.png")
        result = {
            "name": case["name"], "capture": str(case["capturePath"]), "state": str(case["statePath"]),
            "captureSize": list(image.size), "cropBBox": list(crop_bbox),
            "rawSkyGridCells": own_raw, "erodedSkyGridCells": own_eroded,
            "visibleSkyFractionReported": state.get("visibleSkyFraction"),
            "skyMaskIsOnlySky": state.get("skyMaskIsOnlySky"),
            "finalViewPostProcess": exposure,
            "cloudParameters": state.get("cloudParameters"),
            "cloudMaterial": state.get("cloudMaterial"),
            "diagnosticCVars": diagnostic_cvars(state),
            "cloudiness": state.get("cloudiness"),
            "cloudLayerBottomKm": state.get("cloudLayerBottomKm"),
            "cloudLayerHeightKm": state.get("cloudLayerHeightKm"),
            "cloudShadowViewSampleScale": state.get("cloudShadowViewSampleScale"),
            "cloudShadowTracingDistanceKm": state.get("cloudShadowTracingDistanceKm"),
            "cloudAnimationSeconds": state.get("cloudAnimationSeconds"),
            "cloudDriftUV": state.get("cloudDriftUV"),
            "sunLux": state.get("sunLux"), "fogDensity": state.get("fogDensity"),
            "atmosphereMieScale": state.get("atmosphereMieScale"),
            "metrics": stats,
            "comparisonVsBaseline": comparison,
            "metricDifferenceVsBaseline": {
                name: stats[name] - reference_stats[name]
                for name in ("luminanceMean", "luminanceStd", "p5", "p95", "p5P95MichelsonContrast", "fractionLuminanceGe250")
            } if comparison["status"] != "rejected" else None,
            "outputs": {"originalCrop": str(prefix) + "-crop.png", "skyOnly": str(prefix) + "-only.png",
                        "mask": str(prefix) + "-mask.png", "overlay": str(prefix) + "-overlay.png"},
        }
        results.append(result)
        x, y = (index % columns) * tile_width, (index // columns) * tile_height + 70
        drawing.text((x + 12, y + 4), case["name"], fill="white", font=font)
        drawing.text((x + 12, y + 31), f"EV bias {number(exposure.get('exposureBias'), 2)} | adaptation {number(exposure.get('lastEyeAdaptationExposure'), 6)}", fill=(184, 198, 215), font=small_font)
        drawing.text((x + 12, y + 53), f"Mean {stats['luminanceMean']:.1f} | SD {stats['luminanceStd']:.1f} | p5/p95 {stats['p5']:.1f}/{stats['p95']:.1f}", fill=(184, 198, 215), font=small_font)
        drawing.text((x + 12, y + 75), f"Contrast {stats['p5P95MichelsonContrast']:.3f} | lum >=250 {stats['fractionLuminanceGe250']:.1%}", fill=(184, 198, 215), font=small_font)
        sheet.paste(fit_crop(original_crop, panel_size), (x + 12, y + 103))
        sheet.paste(fit_crop(sky_only, panel_size), (x + 20 + panel_size[0], y + 103))
        if comparison["status"] == "rejected":
            drawing.text((x + 12, y + 460), "REJECTED vs baseline: cloud/weather state differs", fill=(255, 138, 118), font=small_font)
        elif comparison["status"] == "shape changed intentionally":
            drawing.text((x + 12, y + 460), "Shape changed intentionally; weather/components match", fill=(235, 201, 130), font=small_font)
        elif comparison["status"] == "lighting changed intentionally":
            drawing.text((x + 12, y + 460), "Lighting changed intentionally; weather/shape match", fill=(235, 201, 130), font=small_font)
        elif comparison["status"] == "shape and lighting changed intentionally":
            drawing.text((x + 12, y + 460), "Shape + lighting changed intentionally; weather matches", fill=(235, 201, 130), font=small_font)
        else:
            drawing.text((x + 12, y + 460), "Cloud/weather state matches baseline within tolerance", fill=(159, 215, 169), font=small_font)
    sheet_path = str(out) + "-contact-sheet.png"
    sheet.save(sheet_path)
    report = {
        "metricUnits": "0-255 screenshot display luminance: Rec.709 weights applied to sRGB channel values; not HDR radiance",
        "erosionGridCells": args.erode_cells,
        "erosionNote": "3x3 minimum filter on depth grid, with zero border; nearest-neighbour resize; common intersection across all cases",
        "maskGridSize": list(reference_mask_size), "captureSize": list(reference_size),
        "commonSkyGridCells": sum(value == 255 for value in pixel_data(common)),
        "commonSkyPixels": sum(value == 255 for value in pixel_data(full_mask)),
        "cropBBox": list(crop_bbox), "contactSheet": sheet_path,
        "baselineCase": reference["name"],
        "allowShapeChange": args.allow_shape_change,
        "allowLightingChange": args.allow_lighting_change,
        "comparisonNote": "Reject if StormClouds, coverage or cloudiness differ by >0.005; density >0.001; layer altitude/height >0.01 km; weather/scene, quality, cloud rendering components or hour differ. Material/layout/spacing/offset/detail changes require --allow-shape-change. Shadow sample scale/distance or supplied color/AO/multiple-scattering differences require --allow-lighting-change. Missing additional lighting audit data remains unknown, not assumed consistent. No metric deltas are emitted for rejected cases.",
        "cases": results, "skipped": skipped,
    }
    report_path = str(out) + "-metrics.json"
    Path(report_path).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    for result in results:
        stats = result["metrics"]
        print(f"{result['name']}: mean={stats['luminanceMean']:.2f}, sd={stats['luminanceStd']:.2f}, p5/p95={stats['p5']:.2f}/{stats['p95']:.2f}, contrast={stats['p5P95MichelsonContrast']:.4f}, lum>=250={stats['fractionLuminanceGe250']:.4f}, comparison={result['comparisonVsBaseline']['status']}")
        if result["comparisonVsBaseline"]["reasons"]:
            print("  incompatible fields:", ", ".join(reason["field"] for reason in result["comparisonVsBaseline"]["reasons"]))
    print("metrics:", report_path)
    print("contact sheet:", sheet_path)


if __name__ == "__main__":
    main()
