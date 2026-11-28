"""Execute the transformed dashboard with mocked browser location and weather APIs."""

import os
import subprocess
import unittest
from pathlib import Path

from build_globe import app


class LocalWeatherTests(unittest.TestCase):
    def run_dashboard(self, source, scenario):
        result = subprocess.run(
            ['node', '-e', BROWSER_TESTS, scenario], input=source, text=True,
            env={**os.environ, 'TZ': 'UTC'}, capture_output=True, check=False, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_location_flows(self):
        self.run_dashboard(app(), 'preview')

    def test_built_extension_location_opt_in(self):
        dashboard = Path(__file__).resolve().parents[1] / 'extension/dashboard.js'
        self.run_dashboard(dashboard.read_text(encoding='utf-8'), 'extension')


BROWSER_TESTS = r"""
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const app = fs.readFileSync(0, 'utf8');
const flush = () => new Promise(setImmediate);
const manualKey = 'local-almanac.manual-home.v1';
const legacyKey = 'local-almanac.place.v1';
const deviceKey = 'home-new-tab.device-home.v1';
const manual = {name: 'Paris', label: 'Paris, France', lat: 48.857, lon: 2.352, zone: 'Europe/Paris'};

class Element {
  constructor() {
    this.children = [];
    this.attrs = new Map();
    this.dataset = {};
    this.listeners = new Map();
    this.classList = {toggle() {}};
    this.style = {setProperty() {}};
  }
  get textContent() { return (this.text || '') + this.children.map(node => node.textContent).join(''); }
  set textContent(text) { this.text = text; this.children = []; }
  setAttribute(name, value) { this.attrs.set(name, value); }
  removeAttribute(name) { this.attrs.delete(name); }
  addEventListener(type, callback, {capture = false} = {}) {
    if (!this.listeners.has(type)) this.listeners.set(type, []);
    this.listeners.get(type).push({callback, capture});
  }
  emit(type, fields = {}) {
    let stopped = false;
    const event = {preventDefault() {}, stopImmediatePropagation() {stopped = true;}, ...fields};
    for (const {callback} of [...(this.listeners.get(type) || [])].sort((a, b) => b.capture - a.capture)) {
      if (stopped) break;
      callback(event);
    }
  }
  replaceChildren(...children) { this.text = ''; this.children = children; }
  contains(node) { return this === node || this.children.some(child => child.contains?.(node)); }
  append(...children) { this.children.push(...children); }
  showModal() { this.open = true; }
  close() { this.open = false; this.emit('close'); }
  focus() {}
}

function start({grant = 'prompt', extension = false, optIn = false, storage = new Map(), offline = false,
                holdManualForecast = false} = {}) {
  const elements = new Map();
  const ui = (id) => {
    if (!elements.has(id)) elements.set(id, new Element());
    return elements.get(id);
  };
  const text = (id) => ui(id).textContent;
  const clock = (city) => ui('clocks').children.find(button => button.children[0].textContent === city);
  const requests = [], positions = [], permissions = [], globe = [], observers = [], sunStarts = [], pendingWeather = [];
  const window = new Element();
  window.AlmanacGlobe = {
    setPlace(place, pins) { globe.push({place, pins}); },
    centerPlace() { globe.push('center'); },
  };
  ui('globe').addEventListener('keydown', () => globe.push('legacy keyboard'));
  const navigator = {
    permissions: {async query({name}) { permissions.push(['query', name]); return {state: grant}; }},
    geolocation: {getCurrentPosition(ok, fail) { positions.push({ok, fail}); }},
  };
  const chrome = extension ? {
    runtime: {id: 'fake-extension'},
    permissions: {
      async contains({permissions: [name]}) { permissions.push(['contains', name]); return grant === 'granted'; },
      async request({permissions: [name]}) { permissions.push(['request', name]); return optIn; },
    },
  } : undefined;
  const document = new Element();
  Object.assign(document, {
    getElementById: ui, createElement: () => new Element(), createElementNS: () => new Element(),
    createTextNode(textContent) { return {textContent}; },
  });
  const Astronomy = {
    Body: {Sun: 'Sun', Moon: 'Moon'},
    Observer: function (lat, lon) { observers.push([lat, lon]); },
    SearchRiseSet(body, observer, dir, begin) {
      sunStarts.push(begin.getUTCHours());
      return {date: new Date(begin.getTime() + (dir > 0 ? 6 : 18) * 3600_000)};
    },
    MoonPhase: () => 0, Illumination: () => ({phase_fraction: 0}),
    Equator: () => ({ra: 0, dec: 0}), HourAngle: () => 0, Libration: () => ({elat: 0, elon: 0}),
    RotationAxis: () => ({ra: 0, dec: 90}), GeoVector: () => ({}), EquatorFromVector: () => ({ra: 0, dec: 0}),
  };
  vm.runInNewContext(app, {
    document, navigator, window, chrome, Astronomy, URL, URLSearchParams, AbortController,
    localStorage: {getItem: (key) => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key)},
    setInterval() {}, setTimeout() {}, clearTimeout() {}, requestAnimationFrame() {}, cancelAnimationFrame() {}, matchMedia: () => ({matches: true}),
    async fetch(url, options) {
      requests.push(url);
      if (url.pathname === '/v1/search') return {ok: true, json: async () => ({results: [
        {name: 'Paris', country: 'France', latitude: manual.lat, longitude: manual.lon, timezone: manual.zone},
      ]})};
      if (offline) throw new Error('Offline');
      const forecast = (temp, timezone) => ({ok: true, json: async () => ({timezone,
        current: {temperature_2m: temp, weather_code: 0, is_day: 1},
      })});
      if (holdManualForecast && url.searchParams.get('latitude') === '48.86') {
        return new Promise((resolve) => pendingWeather.push({signal: options.signal,
          resolve: () => resolve(forecast(99, manual.zone)),
        }));
      }
      return forecast(17, 'America/Los_Angeles');
    },
  });
  return {ui, text, clock, requests, positions, permissions, globe, observers, sunStarts, pendingWeather,
    forecasts: () => requests.filter(url => url.pathname === '/v1/forecast'),
    coords: () => requests.filter(url => url.pathname === '/v1/forecast')
      .map(url => [url.searchParams.get('latitude'), url.searchParams.get('longitude')]),
  };
}

const gps = (position) => position.ok({coords: {latitude: 37.7749, longitude: -122.4194}});
const search = async (page) => {
  page.ui('city-query').value = 'Paris';
  page.ui('city-query').emit('input');
  page.ui('city-search').emit('submit');
  await flush();
  page.ui('city-results').children[0].children[0].emit('click');
  await flush();
};

(async () => {
  if (process.argv[1] === 'extension') {
    const storage = new Map();
    const extension = start({extension: true, grant: 'granted', storage});
    await flush();
    assert.equal(extension.positions.length, 0, 'Chrome permission is not in-app consent');
    assert.equal(extension.forecasts().length, 0);
    extension.ui('weather-place').emit('click');
    extension.ui('locate').emit('click');
    assert.equal(extension.positions.length, 1);
    gps(extension.positions[0]);
    await flush();
    assert.equal(extension.text('place-name'), 'Current location');
    assert.deepEqual(extension.coords(), [['37.77', '-122.42']]);
    assert.deepEqual(JSON.parse(storage.get(deviceKey)), {name: 'Current location', lat: 37.77, lon: -122.42});
    const fallback = start({extension: true, grant: 'granted', storage});
    await flush();
    fallback.positions[0].fail({code: 2});
    assert.equal(fallback.text('place-name'), 'Last known location');
    assert.deepEqual(fallback.coords(), [['37.77', '-122.42']]);
    const moved = start({extension: true, grant: 'granted', storage});
    await flush();
    moved.positions[0].ok({coords: {latitude: 48.857, longitude: 2.352}});
    await flush();
    assert.deepEqual(moved.coords(), [['37.77', '-122.42'], ['48.86', '2.35']]);
    assert.equal(JSON.parse(storage.get(deviceKey)).lat, 48.86);
    moved.ui('weather-place').emit('click');
    await search(moved);
    assert.equal(storage.has(deviceKey), false);
    assert.equal(start({extension: true, storage}).text('place-name'), 'Paris');
    return;
  }
  const storage = new Map([[legacyKey, JSON.stringify({name: 'London', lat: 51.5, lon: -0.1, zone: 'Europe/London'})]]);
  const prompt = start({storage});
  await flush();
  assert.deepEqual(prompt.permissions, [['query', 'geolocation']]);
  assert.equal(prompt.positions.length, 0);
  assert.equal(prompt.forecasts().length, 0);
  assert.equal(prompt.text('place-name'), 'Set location');
  assert.equal(prompt.text('sunrise'), '—');
  prompt.clock('Tokyo').emit('click');
  assert.equal(prompt.globe.at(-2).place.name, 'Tokyo');
  assert.equal(prompt.forecasts().length, 0);
  prompt.ui('globe-home').emit('click');
  assert.equal(prompt.ui('location-dialog').open, true);
  assert.equal(prompt.positions.length, 0);
  prompt.ui('locate').emit('click');
  assert.equal(prompt.positions.length, 1, 'site gesture starts geolocation synchronously');
  prompt.positions[0].fail({code: 1});
  assert.match(prompt.text('location-status'), /denied/);
  await search(prompt);
  assert.equal(prompt.text('place-name'), manual.label);
  assert.deepEqual(prompt.coords(), [['48.86', '2.35']]);
  assert.deepEqual(JSON.parse(storage.get(manualKey)), manual);
  const sunrise = prompt.text('sunrise');
  assert.notEqual(sunrise, '—');
  prompt.clock('Tokyo').emit('click');
  assert.equal(prompt.clock('Tokyo').attrs.get('aria-pressed'), 'true');
  assert.equal(prompt.globe.at(-2).place.name, 'Tokyo');
  assert.equal(prompt.globe.at(-2).pins.at(-1).name, 'Paris');
  assert.equal(prompt.text('sunrise'), sunrise);
  assert.equal(prompt.text('place-name'), manual.label);
  assert.equal(prompt.text('weather-temp'), '17');
  assert.equal(prompt.forecasts().length, 1, 'world clock clicks never fetch foreign weather');
  prompt.ui('globe-home').emit('click');
  assert.equal(prompt.globe.at(-2).place.name, 'Paris');
  assert.equal(prompt.globe.at(-1), 'center');
  assert.equal(prompt.clock('Tokyo').attrs.get('aria-pressed'), 'false');
  prompt.ui('globe-home').emit('click');
  assert.equal(prompt.globe.at(-1), 'center', 'Home recenters even if already selected');
  prompt.clock('Tokyo').emit('click');
  prompt.ui('globe').emit('keydown', {key: 'Home'});
  assert.equal(prompt.globe.at(-2).place.name, 'Paris');
  assert.equal(prompt.globe.at(-1), 'center');
  assert.equal(prompt.forecasts().length, 1);

  const denied = start({extension: true, grant: 'denied', storage});
  await flush();
  assert.deepEqual(denied.permissions, [['contains', 'geolocation']]);
  assert.equal(denied.positions.length, 0);
  assert.deepEqual(denied.coords(), [['48.86', '2.35']]);
  denied.ui('weather-place').emit('click');
  denied.ui('locate').emit('click');
  assert.deepEqual(denied.permissions.at(-1), ['request', 'geolocation']);
  await flush();
  assert.equal(denied.positions.length, 0);
  assert.match(denied.text('location-status'), /denied/);
  assert.equal(denied.text('place-name'), manual.label);

  const allowed = start({extension: true, grant: 'granted', storage, holdManualForecast: true});
  await flush();
  assert.deepEqual(allowed.permissions, [['contains', 'geolocation']]);
  allowed.clock('Tokyo').emit('click');
  gps(allowed.positions[0]);
  await flush();
  assert.equal(allowed.globe.at(-1).place.name, 'Tokyo', 'background GPS must not replace explored city');
  assert.equal(allowed.text('place-name'), 'Current location');
  assert.deepEqual(allowed.coords(), [['48.86', '2.35'], ['37.77', '-122.42']]);
  assert.equal(allowed.pendingWeather[0].signal.aborted, true);
  allowed.pendingWeather[0].resolve();
  await flush();
  assert.equal(allowed.text('weather-temp'), '17');
  assert.ok([7, 8].includes(allowed.sunStarts.at(-1)), 'online sun uses the GPS forecast time zone');
  assert.deepEqual(JSON.parse(storage.get(manualKey)), manual, 'GPS never overwrites the manual fallback');
  allowed.ui('globe-home').emit('click');
  assert.equal(allowed.globe.at(-2).place.name, 'Current location');
  assert.equal(allowed.globe.at(-1), 'center');

  const offline = start({grant: 'granted', offline: true});
  await flush();
  gps(offline.positions[0]);
  await flush();
  assert.equal(offline.text('place-name'), 'Current location');
  assert.equal(offline.text('weather-condition'), 'Weather unavailable');
  assert.equal(offline.text('sunrise'), '06:00 AM');
  assert.equal(offline.sunStarts.at(-1), 0, 'offline sun uses the UTC device time zone');
  assert.deepEqual(offline.observers.at(-1), [37.77, -122.42]);

  const explicit = start({extension: true, optIn: true});
  await flush();
  explicit.ui('weather-place').emit('click');
  explicit.ui('locate').emit('click');
  await flush();
  assert.deepEqual(explicit.permissions, [['contains', 'geolocation'], ['request', 'geolocation']]);
  gps(explicit.positions[0]);
  await flush();
  assert.equal(explicit.text('place-name'), 'Current location');
  assert.equal(explicit.ui('location-dialog').open, false);

  const stale = start({grant: 'granted'});
  await flush();
  stale.ui('weather-place').emit('click');
  await search(stale);
  gps(stale.positions[0]);
  await flush();
  assert.equal(stale.text('place-name'), manual.label, 'late GPS cannot overwrite a new manual city');
  assert.deepEqual(stale.coords(), [['48.86', '2.35']]);
})().catch(error => { console.error(error); process.exitCode = 1; });
"""
