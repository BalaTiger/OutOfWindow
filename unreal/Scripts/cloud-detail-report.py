"""Measure cloud-interior variation in a fixed-exposure, rain-glass-free ROI.

Run cloud-ab-report.py first to generate the common eroded sky mask. This tool
low-passes display luminance at 3 px, removes a fitted linear brightness plane,
and reports residual variation inside the same upper-cloud ROI. It is a lookdev
metric, not HDR radiance or proof of meteorological accuracy. PIL + stdlib only.
"""
import argparse
import json
import math
import statistics
from pathlib import Path

from PIL import Image, ImageFilter


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('cases', nargs='+')
    parser.add_argument('--roi', nargs=4, type=int, default=[450, 65, 576, 215],
                        metavar=('X0', 'Y0', 'X1', 'Y1'))
    args = parser.parse_args()
    root = args.directory.resolve()
    mask = Image.open(root / 'cloud-ab-common-sky-mask.png').convert('L')
    x0, y0, x1, y1 = args.roi
    if not 0 <= x0 < x1 <= mask.width or not 0 <= y0 < y1 <= mask.height:
        parser.error('ROI must be inside the captures')
    points = [(x, y) for y in range(y0, y1) for x in range(x0, x1) if mask.getpixel((x, y)) == 255]
    if len(points) < 100:
        parser.error('ROI has too few common eroded sky samples')
    mx = statistics.fmean(x for x, y in points)
    my = statistics.fmean(y for x, y in points)
    dx, dy = [x - mx for x, y in points], [y - my for x, y in points]
    xx, yy = sum(x*x for x in dx), sum(y*y for y in dy)
    xy = sum(x*y for x, y in zip(dx, dy))
    determinant = xx*yy - xy*xy
    if determinant <= 0:
        parser.error('Degenerate ROI')
    results, reference_exposure = [], None
    for name in args.cases:
        state = read(root / (name + '.json'))
        exposure = state['finalViewPostProcess']
        if exposure['minBrightness'] != exposure['maxBrightness'] or state['windowRainIntensity'] != 0:
            parser.error(name + ' must lock exposure and disable rain glass')
        actual_exposure = exposure['lastEyeAdaptationExposure']
        if reference_exposure is None:
            reference_exposure = actual_exposure
        elif abs(actual_exposure-reference_exposure) > 1e-7:
            parser.error(name + ' has a different actual exposure')
        source = Image.open(state['capture']).convert('RGB')
        if source.size != mask.size:
            parser.error(name + ' has different dimensions')
        # Depth-mask erosion provides ~10 px of margin from roof/frame edges.
        # A 3 px blur suppresses reconstruction grain before measuring lobes.
        gray = Image.new('L', source.size)
        pixels = source.get_flattened_data() if hasattr(source, 'get_flattened_data') else source.getdata()
        gray.putdata([round(r*.2126 + g*.7152 + b*.0722) for r, g, b in pixels])
        gray = gray.filter(ImageFilter.GaussianBlur(3))
        values = [gray.getpixel(p) for p in points]
        mean = statistics.fmean(values)
        xz = sum(x*(z-mean) for x, z in zip(dx, values))
        yz = sum(y*(z-mean) for y, z in zip(dy, values))
        ax, ay = (xz*yy-yz*xy)/determinant, (yz*xx-xz*xy)/determinant
        residuals = [z-mean-ax*x-ay*y for z, x, y in zip(values, dx, dy)]
        rms = math.sqrt(statistics.fmean(v*v for v in residuals))
        results.append(dict(case=name, meanLuminance=mean, fittedPlaneSlopeX=ax,
            fittedPlaneSlopeY=ay, residualRMS=rms, residualRMSOverMean=rms/mean,
            actualExposure=actual_exposure, minEV=exposure['minBrightness'],
            cloudParameters=state['cloudParameters']))
        print(f'{name}: interior residual RMS={rms:.3f}/255, mean={mean:.2f}, normalized={rms/mean:.5f}')
    report = dict(roi=args.roi, commonPixels=len(points), gaussianSigmaPixels=3,
        method='Rec709 display-channel luminance, 3 px Gaussian blur, least-squares linear plane subtraction within common depth-eroded upper-sky ROI.',
        note='The whole-sky contrast includes the large cloud-base gradient; this ROI metric targets non-linear interior variation. Temporal antialiasing and finite sampling remain.',
        cases=results)
    (root / 'cloud-interior-metrics.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')


if __name__ == '__main__':
    main()
