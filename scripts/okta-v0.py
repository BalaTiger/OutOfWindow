"""V0: measure visible-sky cloud cover (okta) from an OOWCapture state json.

    python okta-v0.py <state.json> [more.json ...]

Uses only what the capture already exports: the depth-derived skyMask (which
pixels are sky/cloud, i.e. far plane at base pass) and the PNG. Within the mask
it splits clear from cloud with one stated rule, not a per-image tuned one:

    clear = chroma >= 12, i.e. a channel leads the opposite one by >= 12
            (blue sky B>>R, or sun-side warm sky R>>B), and luminance >= 60
    cloud = everything else (grey/white deck: R~G~B and bright)

Rationale: an earlier rule (bright AND neutral => cloud) flagged the pale-blue
clear sky itself as cloud, so a CloudCover 0..100 sweep moved the measured okta
by under 1 (7.2..7.9) while the same sky's blue fraction moved 37%..1%. That
rule cannot tell a blue clear sky from a white deck; this one keys on the chroma
that actually separates them. Thresholds are fixed here so the number is
comparable across captures; run with --dump to see the distributions if a case
looks misclassified. Okta = (1 - clear fraction) * 8.
"""
import json
import sys
from pathlib import Path

from PIL import Image


def decode_mask(state):
    w, h = state.get("skyMaskWidth", 0), state.get("skyMaskHeight", 0)
    raw = bytes.fromhex(state.get("skyMask") or "")
    if w <= 0 or h <= 0 or len(raw) != w * h:
        return None
    return Image.frombytes("L", (w, h), raw)


def selftest():
    """One runnable check for the classifier rule: blue + warm sky out, white deck in."""
    from io import BytesIO
    img = Image.new("RGB", (2, 2))
    # two clear sky cells (pale blue, warm sun-side) and two cloud cells (grey/white deck)
    img.putdata([(205, 218, 232), (240, 231, 208), (238, 238, 239), (245, 245, 245)])
    buf = BytesIO(); img.save(buf, "PNG")
    state = {"skyMaskWidth": 2, "skyMaskHeight": 2, "skyMask": "ffffffff"}
    mask = decode_mask(state)
    assert mask is not None and mask.size == (2, 2)
    px = img.load(); mk = mask.load()
    clear = [px[x, y] for y in range(2) for x in range(2) if mk[x, y] == 255 and is_clear(px[x, y])]
    assert clear == [(205, 218, 232), (240, 231, 208)], clear  # sky out, deck stays cloud
    print("selftest ok")


def main(argv):
    if "--selftest" in argv:
        selftest(); return 0
    dump = "--dump" in argv
    paths = [a for a in argv[1:] if not a.startswith("--")]
    print(f"{'case':22} {'sky%':>6} {'maskN':>6} {'cloudN':>6} {'okta':>5}  {'medianRGB':>16}")
    for p in paths:
        with open(p, encoding="utf-8-sig") as fh:
            state = json.load(fh)
        capture = Path(state["capture"])
        if not capture.is_file():
            capture = Path(p).with_suffix(".png")
        image = Image.open(capture).convert("RGB")
        mask = decode_mask(state)
        if mask is None:
            print(f"{Path(p).stem:22} no skyMask")
            continue
        # Nearest resize: each mask cell is one sample of the same view rect.
        mask = mask.resize(image.size, Image.NEAREST)
        px, mk = image.load(), mask.load()
        samples = [px[x, y] for y in range(image.height) for x in range(image.width) if mk[x, y] == 255]
        if not samples:
            print(f"{Path(p).stem:22} empty mask")
            continue
        cloud = [c for c in samples if not is_clear(c)]
        frac = len(cloud) / len(samples)
        mid = sorted(samples)[len(samples) // 2]
        print(f"{Path(p).stem:22} {len(samples) / (image.width * image.height):6.3f} "
              f"{len(samples):6d} {len(cloud):6d} {frac * 8:5.1f}  {str(mid):>16}")
        if dump:
            step = max(1, len(samples) // 40)
            for c in samples[::step]:
                print(f"    rgb={c} lum={lum(c):6.1f} chroma={chroma(c):+4d} "
                      f"{'clear' if is_clear(c) else 'cloud'}")
    return 0


def lum(c):
    return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]


def chroma(c):
    """Signed blue-minus-red: positive is blue sky, negative is warm sun-side sky."""
    return c[2] - c[0]


# Fixed thresholds. CHROMA_MIN: a channel must lead the opposite one this much to
# count as sky. LUM_MIN: below this it reads as a wall/shadow, never sky.
CHROMA_MIN, LUM_MIN = 12, 60


def is_clear(c):
    """Sky, not cloud: either a blue-led or a warm-led pixel, bright enough."""
    return abs(chroma(c)) >= CHROMA_MIN and lum(c) >= LUM_MIN


if __name__ == "__main__":
    sys.exit(main(sys.argv))
