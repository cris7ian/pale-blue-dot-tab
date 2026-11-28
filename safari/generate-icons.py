#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10"
# dependencies = ["pillow==12.0.0", "playwright==1.65.2"]
# ///
"""Render the Safari extension and app icons from the Chrome Web Store icon.

Usage: uv run safari/generate-icons.py --chromium /path/to/chromium
"""

from argparse import ArgumentParser
from io import BytesIO
import json
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / 'experiments' / 'store' / 'icon.svg'
APP = HERE / 'Pale Blue Dot Tab'
EXTENSION_SIZES = (48, 96, 128, 256, 512)
APP_ICONS = [(size, scale) for size in (16, 32, 128, 256, 512) for scale in (1, 2)]


def render(chromium):
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=str(chromium))
        page = browser.new_page(viewport={'width': 128, 'height': 128}, device_scale_factor=8)
        page.goto(SOURCE.as_uri())
        master = Image.open(BytesIO(page.screenshot(omit_background=True))).convert('RGBA')
        browser.close()
    return master


def save(master, pixels, path):
    art = master.resize((pixels, pixels), Image.Resampling.LANCZOS)
    # Keep Lanczos ringing out of the transparent padding, as the Store icons do.
    inset = pixels // 8
    padded = Image.new('RGBA', (pixels, pixels))
    padded.paste(art.crop((inset, inset, pixels - inset, pixels - inset)), (inset, inset))
    path.parent.mkdir(parents=True, exist_ok=True)
    padded.save(path, optimize=True)


def main():
    parser = ArgumentParser()
    parser.add_argument('--chromium', required=True, type=Path)
    master = render(parser.parse_args().chromium)
    for size in EXTENSION_SIZES:
        save(master, size, HERE / 'Icons' / f'icon-{size}.png')

    icon_set = APP / 'Assets.xcassets' / 'AppIcon.appiconset'
    images = []
    for size, scale in APP_ICONS:
        name = f'icon_{size}x{size}{"@2x" if scale == 2 else ""}.png'
        save(master, size * scale, icon_set / name)
        images.append({'filename': name, 'idiom': 'mac', 'scale': f'{scale}x', 'size': f'{size}x{size}'})
    (icon_set / 'Contents.json').write_text(json.dumps(
        {'images': images, 'info': {'author': 'xcode', 'version': 1}}, indent=2) + '\n')

    save(master, 384, APP / 'Resources' / 'Icon.png')


if __name__ == '__main__':
    main()
