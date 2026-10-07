"""Tomie -> portrait.txt. Pillow-only, no cv2/rembg."""
import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for _c in (ROOT / "assets" / "tomie.jpg", ROOT / "tomie.jpg", ROOT / "assets" / "me.jpg"):
    if _c.exists():
        SRC = _c
        break
OUT = ROOT / "assets" / "portrait.txt"

RAMP = " `.:~;=+?|)]oX#%&@"
CELL_ASPECT = 0.52
# ponytail: fixed box crop, no auto face-detect/rembg — re-tune BOX if you swap image
BOX = (140, 30, 700, 700)


def convert(cols: int = 80, box: tuple = BOX, gamma: float = 1.0) -> list[str]:
    from PIL import Image, ImageEnhance

    im = Image.open(SRC).convert("L")
    x0, y0, x1, y1 = box
    im = im.crop((x0, y0, x1, y1))
    im = ImageEnhance.Contrast(im).enhance(1.4)  # line-art wants punch
    w, h = im.size
    rows = max(1, round(cols * h / w * CELL_ASPECT))
    im = im.resize((cols, rows), Image.LANCZOS)
    px = list(im.getdata())
    n = len(RAMP) - 1
    # dark ink -> dense char; white bg -> space
    lines = []
    for r in range(rows):
        row = px[r * cols:(r + 1) * cols]
        lines.append("".join(RAMP[min(n, int(((255 - v) / 255) ** gamma * n + 0.5))] for v in row).rstrip())
    while lines and not lines[-1]:
        lines.pop()
    return lines


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cols", type=int, default=60)
    ap.add_argument("--box", type=int, nargs=4, default=BOX)
    ap.add_argument("--gamma", type=float, default=1.0)
    args = ap.parse_args()
    lines = convert(args.cols, tuple(args.box), args.gamma)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"{len(lines)} rows x {max(map(len, lines))} cols -> {OUT.relative_to(ROOT)} from {SRC.name}")


if __name__ == "__main__":
    main()
