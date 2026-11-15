"""Regenerate the README screenshots in docs/images/ from the built-in preview.

    python3 scripts/screenshots.py

Renders the default status line (with the agents rows) and the configurator to ANSI, turns that
into HTML the way a terminal draws it (◤ and ▓▒░ fill the whole cell), shoots it with headless
Chrome (google-chrome or chromium) and crops the background off with Pillow.
"""
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile

BASE = ["#2e3436", "#cc0000", "#4e9a06", "#c4a000", "#3465a4", "#75507b", "#06989a", "#d3d7cf",
        "#555753", "#ef2929", "#8ae234", "#fce94f", "#729fcf", "#ad7fa8", "#34e2e2", "#eeeeec"]

def c256(n):
    if n < 16:
        return BASE[n]
    if n < 232:
        n -= 16
        steps = [0, 95, 135, 175, 215, 255]
        return "#%02x%02x%02x" % (steps[n // 36], steps[(n // 6) % 6], steps[n % 6])
    v = 8 + (n - 232) * 10
    return "#%02x%02x%02x" % (v, v, v)

FG, BG = "#d0d0d0", "#1d1f21"

def mix(a, b, t):
    a = [int(a[i:i + 2], 16) for i in (1, 3, 5)]; b = [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x * t + y * (1 - t)) for x, y in zip(a, b))

SHADES = {"\u2591": .25, "\u2592": .5, "\u2593": .75}
CELL = "display:inline-block;height:1.35em;line-height:1.35em;vertical-align:top;"

def convert(text):
    out = []
    state = {}
    def span(t):
        if not t:
            return
        fg = state.get("fg", FG); bg = state.get("bg")
        if state.get("rev"):
            fg, bg = (bg or BG), fg
        style = CELL + f"color:{fg};"
        if bg: style += f"background:{bg};"
        if state.get("bold"): style += "font-weight:bold;"
        if state.get("dim"): style += "opacity:.6;"
        if state.get("it"): style += "font-style:italic;"
        # Terminals draw these glyphs over the whole cell; fonts in a browser do not.
        cell_bg = bg or BG
        for part in re.split("([\u25e4\u2591\u2592\u2593\n])", t):
            if not part:
                continue
            if part == "\n":
                out.append("\n")
            elif part == "\u25e4":
                out.append(f'<span style="{CELL}width:1ch;background:linear-gradient(to bottom right,{fg} 50%,{cell_bg} 50%)"></span>')
            elif part in SHADES:
                out.append(f'<span style="{CELL}width:1ch;background:{mix(fg, cell_bg, SHADES[part])}"></span>')
            else:
                out.append(f'<span style="{style}">{html.escape(part)}</span>')
    pos = 0
    for m in re.finditer(r"\033\[([0-9;]*)m", text):
        span(text[pos:m.start()]); pos = m.end()
        codes = [int(c) if c else 0 for c in m.group(1).split(";")]
        i = 0
        while i < len(codes):
            c = codes[i]
            if c == 0: state.clear()
            elif c == 1: state["bold"] = 1
            elif c == 2: state["dim"] = 1
            elif c == 3: state["it"] = 1
            elif c == 7: state["rev"] = 1
            elif c == 22: state.pop("bold", None); state.pop("dim", None)
            elif c == 27: state.pop("rev", None)
            elif 30 <= c <= 37: state["fg"] = BASE[c - 30]
            elif 90 <= c <= 97: state["fg"] = BASE[c - 82]
            elif 40 <= c <= 47: state["bg"] = BASE[c - 40]
            elif c == 39: state.pop("fg", None)
            elif c == 49: state.pop("bg", None)
            elif c in (38, 48) and i + 2 < len(codes) and codes[i + 1] == 5:
                state["fg" if c == 38 else "bg"] = c256(codes[i + 2]); i += 2
            i += 1
    span(text[pos:])
    return "".join(out)



def page(text):
    return f'''<!DOCTYPE html><html><head><meta charset="utf-8"><style>
body{{margin:0;background:{BG};}}
pre{{margin:0;padding:14px 18px;font:15px/1.35 "DejaVu Sans Mono",monospace;color:{FG};display:inline-block;}}
</style></head><body><pre>{convert(text.rstrip(chr(10)))}</pre></body></html>'''


def shoot(text, out):
    from PIL import Image, ImageChops
    chrome = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if not chrome:
        sys.exit("needs google-chrome or chromium")
    with tempfile.TemporaryDirectory() as tmp:
        html_path, raw = os.path.join(tmp, "page.html"), os.path.join(tmp, "raw.png")
        with open(html_path, "w", encoding="utf-8") as fh:
            fh.write(page(text))
        subprocess.run([chrome, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                        "--force-device-scale-factor=1", "--window-size=1700,1400",
                        f"--screenshot={raw}", f"file://{html_path}"],
                       check=True, capture_output=True)
        im = Image.open(raw).convert("RGB")
    bg = tuple(int(BG[i:i + 2], 16) for i in (1, 3, 5))
    box = ImageChops.difference(im, Image.new("RGB", im.size, bg)).getbbox()
    pad = 16
    im.crop((max(0, box[0] - pad), max(0, box[1] - pad), min(im.width, box[2] + pad),
             min(im.height, box[3] + pad))).save(out, optimize=True)
    print(out)


def main():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.insert(0, root)
    from claude_statusline.config import DEFAULT_FIELDS, Config
    from claude_statusline.configure import Editor
    from claude_statusline.render import preview
    images = os.path.join(root, "docs", "images")
    os.makedirs(images, exist_ok=True)
    shoot(preview(Config(fields=DEFAULT_FIELDS + ["agents"])), os.path.join(images, "statusline.png"))
    shoot("\n".join(Editor(Config()).screen(100)), os.path.join(images, "configure.png"))


if __name__ == "__main__":
    main()
