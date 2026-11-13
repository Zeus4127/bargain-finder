"""Draws the Acreage Finder launcher icon (green hills, sun, fence) at every Android size."""
import os
from PIL import Image, ImageDraw
HERE = os.path.dirname(os.path.abspath(__file__))
def draw(n):
    S = n * 4
    im = Image.new("RGBA", (S, S), (0, 0, 0, 0)); d = ImageDraw.Draw(im)
    d.rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 5, fill=(126, 200, 240))      # sky
    d.ellipse([S * .58, S * .14, S * .86, S * .42], fill=(255, 205, 60))                 # sun
    d.ellipse([-S * .3, S * .52, S * .8, S * 1.4], fill=(92, 178, 92))                   # back hill
    d.ellipse([S * .25, S * .6, S * 1.35, S * 1.5], fill=(47, 125, 79))                  # front hill
    for x in (.18, .34, .5, .66, .82):                                                    # fence posts
        d.rectangle([S * x - S * .018, S * .7, S * x + S * .018, S * .86], fill=(255, 250, 235))
    d.rectangle([S * .14, S * .74, S * .86, S * .765], fill=(255, 250, 235))
    d.rectangle([S * .14, S * .8, S * .86, S * .825], fill=(255, 250, 235))
    mask = Image.new("L", (S, S), 0); ImageDraw.Draw(mask).rounded_rectangle([0, 0, S - 1, S - 1], radius=S // 5, fill=255)
    im.putalpha(mask)
    return im.resize((n, n), Image.LANCZOS)
for name, n in (("mdpi", 48), ("hdpi", 72), ("xhdpi", 96), ("xxhdpi", 144), ("xxxhdpi", 192)):
    p = os.path.join(HERE, "res", "mipmap-" + name); os.makedirs(p, exist_ok=True)
    draw(n).save(os.path.join(p, "ic_launcher.png"))
draw(512).save(os.path.join(HERE, "icon-512.png"))
print("icons written")
