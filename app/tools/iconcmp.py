"""Side-by-side: what the code draws now vs every .ico on disk."""
import os, sys
from pathlib import Path
APP_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(APP_DIR))
from PySide6.QtWidgets import QApplication
QApplication([])
from archvm import icons
from PIL import Image, ImageDraw, ImageFont
import io

fresh = Image.open(io.BytesIO(icons._png_bytes(icons._draw(128)))).convert("RGBA")

cands = [
    ("code now (icons.py)", fresh),
]
for label, path in [
    ("D:\\ArchVM\\app\\assets\\archvm.ico", r"D:\ArchVM\app\assets\archvm.ico"),
    ("D:\\ArchVM\\manager\\archvm.ico", r"D:\ArchVM\manager\archvm.ico"),
    ("repo docs/icons/archvm.ico", r"D:\ArchVM-manager\docs\icons\archvm.ico"),
    ("D:\\ArchVM\\app\\assets\\icon-preview.png", r"D:\ArchVM\app\assets\icon-preview.png"),
]:
    if os.path.exists(path):
        im = Image.open(path)
        if path.endswith(".ico"):
            sizes = im.info.get("sizes") or {im.size}
            im.size = max(sizes)
        im = im.convert("RGBA")
        im.thumbnail((128, 128))
        cands.append((label, im))
    else:
        cands.append((label + "  [missing]", None))

W = 170 * len(cands) + 20
sheet = Image.new("RGB", (W, 200), "#eef2fb")
d = ImageDraw.Draw(sheet)
x = 10
for label, im in cands:
    if im is not None:
        bg = Image.new("RGBA", (128, 128), "#eef2fb")
        bg.alpha_composite(im.resize((128, 128)) if im.size != (128, 128) else im)
        sheet.paste(bg.convert("RGB"), (x + 21, 14))
    d.text((x + 4, 150), label[:26], fill="#101728")
    d.text((x + 4, 164), label[26:52], fill="#6b7692")
    x += 170
sheet.save("docs/icon-audit.png")
print("wrote docs/icon-audit.png", flush=True)
