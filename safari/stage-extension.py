"""Copy the shipped extension into the Safari extension bundle, with Safari changes.

Xcode runs this as a build phase, so the Safari app always packages the current
extension/ folder. Only the copy changes: a Safari manifest, a location refresh that works
without Chrome's permission, and weather that starts at the city of the device's time zone.
Usage: stage-extension.py EXTENSION ICONS DESTINATION
"""

import json
import shutil
import sys
from pathlib import Path

ICON_SIZES = (48, 96, 128, 256, 512)
ZONE_CITIES = Path(__file__).resolve().with_name('zone-cities.json')
HOME = '    let home = readDeviceHome() || readManualHome();\n'
CHROME_PERMISSION = """      try {
        granted = isExtension ? await globalThis.chrome.permissions?.contains(geolocationPermission) :
          (await navigator.permissions?.query({ name: 'geolocation' }))?.state === 'granted';
      } catch { return; }
"""
SAFARI_PERMISSION = """      // Safari has no geolocation extension permission and asks for location itself, so
      // when Chrome's permission is missing, use the page's own location permission.
      try {
        granted = isExtension && await globalThis.chrome.permissions?.contains(geolocationPermission);
      } catch { granted = false; }
      try {
        granted ||= (await navigator.permissions?.query({ name: 'geolocation' }))?.state === 'granted';
      } catch { return; }
"""


def safari_manifest(manifest):
    manifest = dict(manifest)
    manifest['name'] = 'Pale Blue Dot'
    manifest['icons'] = {str(size): f'icon-{size}.png' for size in ICON_SIZES}
    # Safari asks for location itself and has no geolocation extension permission.
    permissions = [name for name in manifest.get('permissions', []) if name != 'geolocation']
    if permissions:
        manifest['permissions'] = permissions
    else:
        manifest.pop('permissions', None)
    # The listed services already permit browser requests via CORS, and Safari would
    # otherwise ask for access to each site. The CSP keeps the same allowlist.
    manifest.pop('host_permissions', None)
    return manifest


def safari_location(dashboard):
    """After the user opts in, refresh the saved location with Safari's own permission."""
    if dashboard.count(CHROME_PERMISSION) != 1:
        raise ValueError('dashboard.js: expected one location permission check')
    return dashboard.replace(CHROME_PERMISSION, SAFARI_PERMISSION)


def zone_home(dashboard):
    """Until a place is chosen, start at the main city of the device's time zone."""
    if dashboard.count(HOME) != 1:
        raise ValueError('dashboard.js: expected one home initialization')
    data = json.loads(ZONE_CITIES.read_text(encoding='utf-8'))
    table = json.dumps({'cities': data['cities'], 'links': data['links']}, separators=(',', ':'))
    return dashboard.replace(HOME, f'''    // Safari: the main city of each time zone, from tz database {data['version']} (zone.tab).
    const zoneCities = {table};

    // Until a place is chosen, show the city of the device's time zone. This reads only the
    // time zone setting, never the device location, and is not saved.
    function zoneHome() {{
      const zone = deviceZone();
      const clock = defaultCities.find((city) => city.zone === zone);
      if (clock) return {{ ...clock }};
      const main = zoneCities.links[zone] || zone;
      const place = zoneCities.cities[main];
      if (!place || !validZone(zone)) return null;
      const name = main.split('/').at(-1).replaceAll('_', ' ');
      return {{ name, lat: place[0], lon: place[1], zone }};
    }}

    let home = readDeviceHome() || readManualHome() || zoneHome();
''')


def stage(extension, icons, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for source in sorted(extension.iterdir()):
        if source.is_file() and source.name != 'manifest.json':
            shutil.copy2(source, destination / source.name)
    for size in ICON_SIZES:
        shutil.copy2(icons / f'icon-{size}.png', destination / f'icon-{size}.png')
    dashboard = (extension / 'dashboard.js').read_text(encoding='utf-8')
    (destination / 'dashboard.js').write_text(zone_home(safari_location(dashboard)), encoding='utf-8')
    manifest = json.loads((extension / 'manifest.json').read_text(encoding='utf-8'))
    (destination / 'manifest.json').write_text(
        json.dumps(safari_manifest(manifest), ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    stage(*(Path(argument) for argument in sys.argv[1:4]))
