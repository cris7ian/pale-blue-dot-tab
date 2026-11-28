"""Check the built Moon view against Astronomy Engine and d3 for known skies."""

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class MoonSkyTests(unittest.TestCase):
    def test_moon_turns_with_the_city_sky(self):
        result = subprocess.run(['node', '-e', SKY_TESTS], cwd=ROOT, text=True,
                                capture_output=True, check=False, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


SKY_TESTS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const CHECKS = String.raw`
const wrap = (degrees) => ((degrees % 360) + 540) % 360 - 180;
const near = (actual, expected, tolerance, message) =>
  assert.ok(Math.abs(wrap(actual - expected)) <= tolerance, message + ': ' + actual.toFixed(1) + '°');

// Which way the lit side faces on screen, clockwise from up, as moonView draws it.
function litBearing(lat, lon, when) {
  const sky = moonSky(when);
  const {projection, night} = moonView(100, sky, moonAngles(when, {lat, lon}, sky));
  let x = 0, y = 0;
  for (let k = 0; k < 72; k++) {
    const a = k * Math.PI / 36, px = 50 + 30 * Math.sin(a), py = 50 - 30 * Math.cos(a);
    if (!d3.geoContains(night, projection.invert([px, py]))) { x += Math.sin(a); y += Math.cos(a); }
  }
  return Math.atan2(x, y) * 180 / Math.PI;
}

const crescent = Astronomy.SearchMoonPhase(45, new Date('2026-12-01T00:00Z'), 40).date;
const transit = (lat, lon) => Astronomy.SearchHourAngle(Astronomy.Body.Moon, new Astronomy.Observer(lat, lon, 0), 0, crescent).time.date;
const beforeSet = (lat, lon) => new Date(Astronomy.SearchRiseSet(Astronomy.Body.Moon, new Astronomy.Observer(lat, lon, 0), -1, crescent, 2).date - 3600_000);

near(moonTilt(transit(48.86, 2.35), {lat: 48.86, lon: 2.35}).zenith, 0, 1, 'Paris has celestial north up at transit');
near(moonTilt(transit(-33.87, 151.21), {lat: -33.87, lon: 151.21}).zenith, 180, 1, 'Sydney has celestial north down at transit');
near(litBearing(48.86, 2.35, transit(48.86, 2.35)), 90, 30, 'Paris sees a waxing Moon lit on the right');
near(litBearing(48.86, 2.35, beforeSet(48.86, 2.35)), 135, 25, 'Paris sees the evening crescent lit lower right');
near(litBearing(-33.87, 151.21, transit(-33.87, 151.21)), -90, 30, 'Sydney sees a waxing Moon lit on the left');
near(litBearing(-0.18, -78.47, beforeSet(-0.18, -78.47)), 180, 25, 'Quito sees the setting crescent lit from below');

// The view: libration centers the sub-Earth point, roll turns lunar north clockwise.
const sky = {libration: {elon: 6, elat: -5}, axis: 0, phase: 90};
let {projection} = moonView(100, sky, {roll: 0, light: 90});
const [lon, lat] = projection.invert([50, 50]);
near(lon, 6, 0.01, 'Libration centers the sub-Earth longitude');
near(lat, -5, 0.01, 'Libration centers the sub-Earth latitude');
({projection} = moonView(100, {...sky, libration: {elon: 0, elat: 0}}, {roll: 30, light: 90}));
const [px, py] = projection([0, 60]);
near(Math.atan2(px - 50, 50 - py) * 180 / Math.PI, 30, 0.01, 'A 30° roll turns lunar north 30° clockwise');
const middle = projection.invert([50, 50]);
assert.ok(!d3.geoContains(moonView(100, {...sky, phase: 1}, {roll: 0, light: 0}).night, middle), 'A full Moon is lit at the center');
assert.ok(d3.geoContains(moonView(100, {...sky, phase: 179}, {roll: 0, light: 0}).night, middle), 'A new Moon is dark at the center');

// The Moon's axis leans at most about 25° from celestial north.
let most = 0;
for (let day = 0; day < 365; day += 3) most = Math.max(most, Math.abs(moonAxis(new Date(Date.UTC(2026, 0, 1 + day)))));
assert.ok(most > 15 && most < 26, 'Axis tilt stays within its range: ' + most.toFixed(1) + '°');
`;
const js = fs.readFileSync('extension/dashboard.js', 'utf8');
const view = js.slice(js.indexOf('    function moonTilt('), js.indexOf('    function paintMoon('));
const sources = ['vendor/astronomy.browser.min.js', 'experiments/globe/d3-array.min.js', 'experiments/globe/d3-geo.min.js'];
// One context, so Astronomy Engine, d3 and the checks share the same Date.
vm.runInNewContext([...sources.map((name) => fs.readFileSync(name, 'utf8')), view, CHECKS].join('\n'), {assert});
"""
