"""Step 0: measure the sky only, using the depth-derived mask the game now exports.

    python sky-mask-report.py <validation.json> [--overlay out.png]

Reports tonal stats over sky pixels alone. Without the mask a "sky brightness"
number cannot be told apart from a roofline one -- that was the flaw in the
previous pass. No numpy: PIL + stdlib only.
"""
import json
import sys
import statistics as st
from PIL import Image

MASK_ON = 255


def load(path):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def mask_image(state):
    hexed = state.get("skyMask") or ""
    w, h = state.get("skyMaskWidth", 0), state.get("skyMaskHeight", 0)
    if not hexed or w <= 0 or h <= 0:
        raise SystemExit("no skyMask in this json -- it predates step 0")
    raw = bytes.fromhex(hexed)
    if len(raw) != w * h:
        raise SystemExit("mask is %d bytes, expected %d" % (len(raw), w * h))
    return Image.frombytes("L", (w, h), raw)


def stats(px, points):
    lum = [0.2126 * px[x, y][0] + 0.7152 * px[x, y][1] + 0.0722 * px[x, y][2] for x, y in points]
    rgb = [sum(px[x, y][c] for x, y in points) / len(points) for c in range(3)]
    ordered = sorted(lum)
    mean = st.mean(lum)
    sd = st.pstdev(lum)
    return {
        "n": len(lum),
        "rgb": rgb,
        "lum": mean,
        "sd": sd,
        "contrast": sd / mean if mean else 0.0,
        "p1": ordered[int(len(lum) * .01)],
        "p5": ordered[int(len(lum) * .05)],
        "p50": ordered[len(lum) // 2],
        "p95": ordered[int(len(lum) * .95)],
        "p99": ordered[int(len(lum) * .99)],
    }


def main(argv):
    state = load(argv[1])
    capture = state["capture"]
    image = Image.open(capture).convert("RGB")
    mask = mask_image(state)
    # The mask is a 128x72 grid over the same view rect, so nearest-neighbour is
    # the honest resize: every box is one sample, no invented intermediates.
    full = mask.resize(image.size, Image.NEAREST)
    mpx, px = full.load(), image.load()
    w, h = image.size

    points = [(x, y) for y in range(h) for x in range(w) if mpx[x, y] >= MASK_ON]
    if not points:
        raise SystemExit("mask selected no pixels")
    cover = len(points) / (w * h)
    print("capture        %s  %dx%d" % (capture, w, h))
    print("mask           %dx%d, all-sky=%s" % (state["skyMaskWidth"], state["skyMaskHeight"], state.get("skyMaskIsOnlySky")))
    print("sky pixels     %d  (%.1f%% of frame; game says visibleSkyFraction=%.4f)"
          % (len(points), cover * 100, state.get("visibleSkyFraction", -1)))
    s = stats(px, points)
    print("sky rgb        %.1f / %.1f / %.1f" % tuple(s["rgb"]))
    print("sky lum        mean %.1f  sd %.1f  contrast %.3f" % (s["lum"], s["sd"], s["contrast"]))
    print("sky p1/p5/p50/p95/p99  %.1f / %.1f / %.1f / %.1f / %.1f"
          % (s["p1"], s["p5"], s["p50"], s["p95"], s["p99"]))
    for t in (80, 120, 160, 200, 230):
        print("  frac >= %3d   %.3f" % (t, sum(1 for x, y in points if 0.2126 * px[x, y][0] + 0.7152 * px[x, y][1] + 0.0722 * px[x, y][2] >= t) / len(points)))

    if "--overlay" in argv:
        out = argv[argv.index("--overlay") + 1]
        tint = image.copy()
        tpx = tint.load()
        for x, y in points:
            tpx[x, y] = (min(255, px[x, y][0] // 2 + 128), px[x, y][1] // 2, px[x, y][2] // 2)
        tint.save(out)
        print("overlay        %s  (red = counted as sky)" % out)
    return 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    sys.exit(main(sys.argv))
