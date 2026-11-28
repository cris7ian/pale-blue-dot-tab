"""Refresh zone-cities.json for the Safari app: the main city of each IANA time zone.

zone.tab gives each zone's principal location. tzdata.zi links map older names that
browsers still report, such as Asia/Calcutta, to the zone they now point to.
Usage: python3 safari/generate-zone-cities.py [/usr/share/zoneinfo]
"""

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def degrees(text, width):
    sign = -1 if text[0] == '-' else 1
    digits = text[1:]
    whole, minutes, seconds = digits[:width], digits[width:width + 2], digits[width + 2:] or '0'
    return sign * (int(whole) + int(minutes) / 60 + int(seconds) / 3600)


def main():
    zoneinfo = Path(sys.argv[1] if len(sys.argv) > 1 else '/usr/share/zoneinfo')
    cities = {}
    for line in (zoneinfo / 'zone.tab').read_text().splitlines():
        if line.startswith('#'):
            continue
        _, coordinates, zone, *_ = line.split('\t')
        lat, lon = re.fullmatch(r'([+-]\d+)([+-]\d+)', coordinates).groups()
        cities[zone] = [round(degrees(lat, 2), 2), round(degrees(lon, 3), 2)]
    links = {}
    for line in (zoneinfo / 'tzdata.zi').read_text().splitlines():
        if line.startswith('L '):
            _, target, alias = line.split()
            if target in cities and alias not in cities:
                links[alias] = target
    version = (zoneinfo / '+VERSION').read_text().strip()
    data = {'version': version, 'cities': dict(sorted(cities.items())), 'links': dict(sorted(links.items()))}
    path = HERE / 'zone-cities.json'
    path.write_text(json.dumps(data, separators=(',', ':')) + '\n')
    print(f'tzdata {version}: {len(cities)} zones, {len(links)} links, {path.stat().st_size:,} bytes')


if __name__ == '__main__':
    main()
