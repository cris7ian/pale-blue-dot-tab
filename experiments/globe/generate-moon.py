#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.10,<3.14"
# dependencies = ["numpy==2.3.4", "pillow==12.0.0", "scikit-image==0.25.2", "shapely==2.1.2"]
# ///
"""Refresh moon-data.js: the lunar maria traced from NASA SVS's Moon mosaic, and major craters.

The mosaic is a north-up view of the near side at zero libration, with lunar east on the right.
Maria are traced at several depths below the brightness of their ring of the disk, which cancels
limb darkening; stacked, the depths fade each sea in from its shore. Each outline is mapped from
the photo onto the sphere, so the globe's projection can draw it. Crater positions and sizes are
from the IAU Gazetteer of Planetary Nomenclature, rounded.
"""

import json
import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from shapely import Polygon, union_all
from shapely.geometry import MultiPolygon, mapping
from shapely.geometry.polygon import orient
from skimage.measure import find_contours

HERE = Path(__file__).resolve().parent
MOSAIC = HERE.parent / 'moon-mosaic.jpg'
# The lunar disk in the mosaic: a circle fitted to its limb, as fractions of the image size.
CENTER, RADIUS = (0.5005, 0.4988), 0.4846
DEPTHS = (0.93, 0.87, 0.81, 0.75)  # brightness relative to the ring, shore to deep sea
EDGE = 0.975         # ignore the limb, where the photo is too foreshortened to read
BLUR = 3             # pixels on the 360 px mosaic
SMALLEST = 1.0       # square degrees
TOLERANCE = 0.4      # degrees: about 0.4 px at the Moon's size on the page
MOON_KM = 1737.4
# name: (latitude, east longitude, diameter in km, look). Looks: bright rays, dark floor, rim.
CRATERS = {
    'Tycho': (-43.3, -11.2, 85, 'bright'), 'Copernicus': (9.6, -20.1, 96, 'bright'),
    'Kepler': (8.1, -38.0, 31, 'bright'), 'Aristarchus': (23.7, -47.5, 40, 'bright'),
    'Proclus': (16.1, 46.8, 28, 'bright'), 'Menelaus': (16.3, 16.0, 26, 'bright'),
    'Plato': (51.6, -9.4, 101, 'dark'), 'Grimaldi': (-5.5, -68.3, 173, 'dark'),
    'Endymion': (53.6, 57.0, 123, 'dark'), 'Riccioli': (-3.0, -74.3, 139, 'dark'),
    'Clavius': (-58.4, -14.4, 225, 'rim'), 'Maginus': (-50.5, -6.3, 194, 'rim'),
    'Longomontanus': (-49.6, -21.9, 145, 'rim'), 'Schickard': (-44.3, -54.6, 206, 'rim'),
    'Ptolemaeus': (-9.3, -1.9, 153, 'rim'), 'Alphonsus': (-13.4, -3.2, 108, 'rim'),
    'Arzachel': (-18.2, -1.9, 96, 'rim'), 'Hipparchus': (-5.1, 5.2, 138, 'rim'),
    'Albategnius': (-11.2, 4.0, 130, 'rim'), 'Walther': (-33.1, 1.0, 132, 'rim'),
    'Theophilus': (-11.4, 26.4, 98, 'rim'), 'Cyrillus': (-13.2, 24.0, 98, 'rim'),
    'Catharina': (-18.1, 23.4, 99, 'rim'), 'Langrenus': (-8.9, 61.1, 132, 'rim'),
    'Petavius': (-25.3, 60.4, 177, 'rim'), 'Furnerius': (-36.0, 60.6, 135, 'rim'),
    'Janssen': (-45.4, 40.3, 199, 'rim'), 'Posidonius': (31.9, 29.9, 95, 'rim'),
    'Archimedes': (29.7, -4.0, 81, 'rim'), 'Eratosthenes': (14.5, -11.3, 58, 'rim'),
    'Gassendi': (-17.6, -40.1, 110, 'rim'), 'Bullialdus': (-20.7, -22.2, 61, 'rim'),
}


def contrast():
    image = Image.open(MOSAIC).convert('L').filter(ImageFilter.GaussianBlur(BLUR))
    pixels = np.asarray(image, dtype=float)
    height, width = pixels.shape
    cx, cy, radius = CENTER[0] * width, CENTER[1] * height, RADIUS * width
    ys, xs = np.mgrid[0:height, 0:width]
    r = np.hypot(xs + 0.5 - cx, ys + 0.5 - cy) / radius
    rings = np.minimum((r * 60).astype(int), 59)
    inside = r < 1
    ring_mean = np.array([pixels[inside & (rings == k)].mean() for k in range(60)])
    ratio = pixels / ring_mean[rings]
    ratio[r >= EDGE] = 2  # highland beyond the readable disk closes every outline
    return ratio, (cx, cy, radius)


def sphere(points, disk):
    cx, cy, radius = disk
    for row, col in points:
        east, north = (col + 0.5 - cx) / radius, (cy - row - 0.5) / radius
        near = math.sqrt(max(0.0, 1 - east * east - north * north))
        yield math.degrees(math.atan2(east, near)), math.degrees(math.asin(max(-1.0, min(1.0, north))))


def depth(ratio, disk, level):
    maria = Polygon()
    for outline in find_contours(ratio, level):
        ring = Polygon(list(sphere(outline, disk)))
        if ring.is_valid and ring.area >= SMALLEST:
            # Even–odd nesting: an outline inside a mare is a highland island.
            maria = maria.symmetric_difference(ring)
    maria = union_all([maria]).simplify(TOLERANCE, preserve_topology=True)
    polygons = [orient(part, sign=-1) for part in getattr(maria, 'geoms', [maria])
                if part.geom_type == 'Polygon' and part.area >= SMALLEST]
    return {'type': 'MultiPolygon', 'coordinates': rounded(mapping(MultiPolygon(polygons))['coordinates'])}


def build():
    ratio, disk = contrast()
    craters = [[lon, lat, round(math.degrees(km / 2 / MOON_KM), 2), look]
               for lat, lon, km, look in CRATERS.values()]
    return {'maria': [depth(ratio, disk, level) for level in DEPTHS], 'craters': craters}


def rounded(item):
    if isinstance(item, (list, tuple)):
        return [rounded(child) for child in item]
    return round(item, 2)


def main():
    data = json.dumps(build(), separators=(',', ':'))
    (HERE / 'moon-data.js').write_text(
        "// Generated by generate-moon.py: maria traced from NASA SVS's Moon mosaic (svs.gsfc.nasa.gov/5001),\n"
        '// craters from the IAU Gazetteer of Planetary Nomenclature.\n'
        f'window.AlmanacMoonData={data};\n', encoding='utf-8')


if __name__ == '__main__':
    main()
