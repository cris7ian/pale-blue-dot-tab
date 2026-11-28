"""Keep the Safari app in step with the shipped Chrome extension."""

import importlib.util
import json
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SAFARI = ROOT / 'safari'
spec = importlib.util.spec_from_file_location('stage_extension', SAFARI / 'stage-extension.py')
stage_extension = importlib.util.module_from_spec(spec)
spec.loader.exec_module(stage_extension)


class SafariPackageTests(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / 'extension' / 'manifest.json').read_text())

    def test_app_version_matches_the_extension(self):
        project = (SAFARI / 'Pale Blue Dot Tab.xcodeproj' / 'project.pbxproj').read_text()
        versions = set(re.findall(r'MARKETING_VERSION = ([^;]+);', project))
        self.assertEqual(versions, {self.manifest['version']})

    def test_stages_every_extension_file_with_a_safari_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder)
            stage_extension.stage(ROOT / 'extension', SAFARI / 'Icons', destination)
            staged = json.loads((destination / 'manifest.json').read_text())
            shipped = {path.name for path in (ROOT / 'extension').iterdir() if path.is_file()}
            self.assertLessEqual(shipped, {path.name for path in destination.iterdir()})
        self.assertEqual(staged['name'], 'Pale Blue Dot')
        self.assertEqual(self.manifest['name'], 'Pale Blue Dot Tab')
        self.assertEqual(staged['chrome_url_overrides'], self.manifest['chrome_url_overrides'])
        self.assertEqual(staged['content_security_policy'], self.manifest['content_security_policy'])
        self.assertNotIn('geolocation', staged.get('permissions', []))
        self.assertNotIn('host_permissions', staged)
        for name in staged['icons'].values():
            self.assertTrue((SAFARI / 'Icons' / name).is_file(), name)

    def test_only_safari_falls_back_to_the_page_location_permission(self):
        chrome = (ROOT / 'extension' / 'dashboard.js').read_text()
        safari = stage_extension.safari_location(chrome)
        self.assertNotIn('granted ||=', chrome)
        self.assertIn('granted ||=', safari)
        # The device location is still read only after the user opts in.
        self.assertIn("if (mode === 'manual' || (isExtension && mode !== 'device')) return;", safari)

    def test_only_safari_starts_at_the_time_zone_city(self):
        chrome = (ROOT / 'extension' / 'dashboard.js').read_text()
        self.assertNotIn('zoneHome', chrome)
        safari = stage_extension.zone_home(chrome)
        start = safari.index('    const zoneCities')
        end = safari.index('    let home = ')
        checks = r"""
const madrid = { name: 'Madrid', lat: 40.42, lon: -3.7, zone: 'Europe/Madrid' };
const defaultCities = [madrid];
const validZone = (zone) => { try { new Intl.DateTimeFormat('en', { timeZone: zone }); return true; } catch { return false; } };
let deviceZone;
const at = (zone) => { deviceZone = () => zone; return zoneHome(); };
const clock = at('Europe/Madrid');
assert.equal(clock.name, 'Madrid'); assert.equal(clock.lat, 40.42);
const legacy = at('Asia/Calcutta');
assert.deepEqual([legacy.name, legacy.lat, legacy.lon, legacy.zone], ['Kolkata', 22.53, 88.37, 'Asia/Calcutta']);
assert.equal(at('America/Argentina/Buenos_Aires').name, 'Buenos Aires');
assert.equal(at('UTC'), null);
"""
        script = ("const assert = require('node:assert/strict');\n" +
                  safari[start:end].replace('function zoneHome', 'var zoneHome = function') + checks)
        result = subprocess.run(['node', '-e', script], text=True, capture_output=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
