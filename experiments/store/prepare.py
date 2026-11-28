"""Prepare and exercise the Chrome Web Store package from the shipped extension."""
from argparse import ArgumentParser
from io import BytesIO
import json
from pathlib import Path
import re
from subprocess import check_output
from zipfile import ZIP_DEFLATED, ZipFile

from PIL import Image
from playwright.sync_api import Error, expect, sync_playwright

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def prepare(package, ref):
    release = check_output(['git', 'archive', '--format=zip', ref, 'extension'], cwd=ROOT)
    with ZipFile(BytesIO(release)) as source:
        for item in source.namelist():
            if not item.endswith('/'):
                (package / Path(item).name).write_bytes(source.read(item))
    manifest_path = package / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())

    manifest['icons'] = {str(size): f'icon-{size}.png' for size in (16, 32, 48, 128)}
    # The listed services already permit browser requests via CORS. Keep the CSP
    # allowlist, but do not ask for host access beyond standard browser fetch.
    manifest.pop('host_permissions', None)
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    page_path = package / 'newtab.html'
    source = page_path.read_text()
    # Current builds include the shared disclosure. Retain support for older tags.
    if 'id="geo-disclosure"' in source:
        return manifest
    anchor = '<button type="button" class="locate" id="locate">Use my location</button>'
    assert source.count(anchor) == 1
    policy = '<p class="geo-disclosure" id="geo-disclosure">Approximate coordinates go to Open-Meteo for weather when you allow location access. You can search for a city instead.</p>'
    source = source.replace(anchor, policy + anchor.replace('id="locate"', 'id="locate" aria-describedby="geo-disclosure"'))
    page_path.write_text(source)
    css = package / 'home.css'
    css.write_text(css.read_text() +
                   '\n.geo-disclosure{font-size:12px;line-height:1.5;color:var(--quiet);margin:0 0 12px}\n'
                   '#geo-disclosure:has(+ #locate[hidden]){display:none}\n')
    return manifest


def main():
    parser = ArgumentParser()
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--chromium', required=True, type=Path)
    parser.add_argument('--ref', default='HEAD', help='Commit or tag to package')
    args = parser.parse_args()
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    package = out / 'package'
    package.mkdir(exist_ok=True)
    manifest = prepare(package, args.ref)
    executable = str(args.chromium)
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path=executable)
        icon = browser.new_page(viewport={'width': 128, 'height': 128}, device_scale_factor=4)
        icon.goto((HERE / 'icon.svg').as_uri())
        master = Image.open(BytesIO(icon.screenshot(omit_background=True))).convert('RGBA')
        for size, name in manifest['icons'].items():
            pixels = int(size)
            art = master.resize((pixels, pixels), Image.Resampling.LANCZOS)
            # Keep Lanczos ringing out of Chrome's transparent padding.
            inset = pixels // 8
            padded = Image.new('RGBA', (pixels, pixels))
            padded.paste(art.crop((inset, inset, pixels - inset, pixels - inset)), (inset, inset))
            padded.save(package / name)
        browser.close()
        profile = out / 'test-profile'
        with p.chromium.launch_persistent_context(str(profile), executable_path=executable,
                viewport={'width': 1280, 'height': 800}, timezone_id='Europe/Madrid',
                args=[f'--disable-extensions-except={package}', f'--load-extension={package}']) as context:
            page = context.new_page()
            errors = []
            page.on('pageerror', lambda e: errors.append(str(e)))
            try:
                page.goto('chrome://newtab/', wait_until='commit')
            except Error as e:
                if 'ERR_ABORTED' not in str(e):
                    raise
            expect(page.locator('#globe')).to_be_visible()
            assert page.evaluate('location.protocol') == 'chrome-extension:'
            assert page.evaluate('chrome.runtime.getManifest().version') == manifest['version']
            page.locator('#weather-place').click()
            expect(page.locator('#geo-disclosure')).to_be_visible()
            page.locator('#city-query').fill('Madrid')
            page.locator('#city-search button[type=submit]').click()
            page.locator('#city-results button').filter(has_text=re.compile('Madrid.*Spain')).first.click(timeout=15000)
            expect(page.locator('#weather-temp')).to_have_text(re.compile(r'^-?\d+$'), timeout=15000)
            expect(page.locator('#globe-iss')).to_have_attribute('aria-disabled', 'false', timeout=15000)
            expect(page.locator('#sunrise')).to_have_text(re.compile(r'^\d{2}:\d{2} (AM|PM)$'))
            page.locator('#settings-open').click()
            page.locator('#add-city-clock').click()
            expect(page.locator('#geo-disclosure')).to_be_hidden()
            page.keyboard.press('Escape')
            page.keyboard.press('Escape')
            page.evaluate('document.fonts.ready')
            for scheme in ('light', 'dark'):
                page.emulate_media(color_scheme=scheme)
                expect(page.locator('html')).to_have_attribute('data-theme', scheme)
                page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')
                screenshot = out / f'pale-blue-dot-tab-{scheme}.png'
                page.screenshot(path=screenshot)
                image = Image.open(screenshot).convert('RGB')
                assert image.size == (1280, 800)
                image.save(screenshot, optimize=True)
            assert not errors, errors
    output = out / f'pale-blue-dot-tab-web-store-{manifest["version"]}.zip'
    with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(package.iterdir()):
            archive.write(path, path.name)
    with ZipFile(output) as archive:
        assert archive.testzip() is None and 'manifest.json' in archive.namelist()
        assert json.loads(archive.read('manifest.json')) == manifest
        store_icon = Image.open(BytesIO(archive.read(manifest['icons']['128'])))
        assert store_icon.size == (128, 128) and store_icon.mode == 'RGBA'
        assert store_icon.getchannel('A').getbbox() == (16, 16, 112, 112)
    print(f'{output} ({output.stat().st_size} bytes)')
    print('Store build tested in Chromium: new-tab override, geocoding, forecast, sunrise and live ISS; light and dark screenshots.')


if __name__ == '__main__':
    main()
