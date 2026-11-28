"""Keep Grid weather and sun independent from globe exploration."""


def _replace(js: str, old: str, new: str) -> str:
    if js.count(old) != 1:
        raise ValueError(f'Expected one Grid dashboard anchor: {old}')
    return js.replace(old, new)


def _block(js: str, start: str, end: str, replacement: str) -> str:
    if js.count(start) != 1 or js.count(end) != 1:
        raise ValueError(f'Expected one Grid dashboard block: {start} … {end}')
    first = js.index(start)
    return js[:first] + replacement + js[js.index(end, first + len(start)):]


def local_weather(js: str) -> str:
    """Transform build_globe.app() output; do not modify the flat dashboard."""
    js = _replace(js, "const storageKey = 'local-almanac.place.v1';", """const storageKey = 'local-almanac.manual-home.v1';
    const legacyStorageKey = 'local-almanac.place.v1';""")
    js = _block(js, '    function readPlace() {', '    function html(', HOME_STATE)
    js = _replace(js, "button.addEventListener('click', () => selectPlace(city));", """button.addEventListener('click', () => {
        explored = city;
        renderGlobe(true);
      });""")
    js = _block(js, '    function matchingCity(', '    const conditions = {', RENDER_HOME)
    js = _replace(js, 'if (!force && (weatherRequest || Date.now() < weatherDue || document.hidden)) return;',
                  'if (!home || (!force && (weatherRequest || Date.now() < weatherDue || document.hidden))) return;')
    js = _replace(js, 'const target = place;', 'const target = home;')
    js = _replace(js, '          savePlace();\n', '')
    js = _replace(js, "    $('weather-place').addEventListener('click', () => {", '    function openLocation() {')
    js = _replace(js, "      query.focus();\n    });", """      query.focus();
    }

    $('weather-place').addEventListener('click', openLocation);
    function returnHome(event) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!home) { openLocation(); return; }
      explored = null;
      renderGlobe(true);
    }
    $('globe-home')?.addEventListener('click', returnHome, { capture: true });
    $('globe')?.addEventListener('keydown', (event) => {
      if (event.key === 'Home' && !event.altKey && !event.ctrlKey && !event.metaKey) returnHome(event);
    }, { capture: true });""")
    js = _block(js, "    locate.addEventListener('click', async () => {",
                "    $('city-search').addEventListener", GEOLOCATION)
    js = _replace(js, '            selectPlace({ name: item.name, label, lat: item.latitude, lon: item.longitude, zone: item.timezone });',
                  """            if (!current()) return;
            const manual = { name: item.name, label, lat: item.latitude, lon: item.longitude, zone: item.timezone };
            saveManualHome(manual);
            selectHome(manual, true);""")
    js = _replace(js, """      if (place.zone) {
        const civilDay = localDay(now, place.zone);
        if (!sun || sun.civilDay !== civilDay) sun = sunForDay(civilDay, place);
      }
      const label = (instant) => instant == null ? '—' : time(instant, place.zone);""", """      const zone = home?.zone || deviceZone();
      if (home) {
        const civilDay = localDay(now, zone);
        if (!sun || sun.civilDay !== civilDay || sun.zone !== zone) {
          sun = { ...sunForDay(civilDay, { ...home, zone }), zone };
        }
      }
      const label = (instant) => instant == null ? '—' : time(instant, zone);""")
    return _replace(js, '    renderPlace();\n    tick();\n    refreshWeather(true);', """    renderHome();
    renderGlobe();
    tick();
    refreshWeather(true);
    locateIfAllowed();""")


def exploring_weather(js: str) -> str:
    """Use an explored city temporarily; keep the saved location separate."""
    js = _replace(js, '    let explored = null;', '    let explored = null;\n    const displayedPlace = () => explored || home;')
    js = _replace(js, '        explored = city;\n        renderGlobe(true);', '        explored = city;\n        renderGlobe(true);\n        switchForecast();')
    js = _replace(js, '      const label = home?.label || home?.name;', '      const view = displayedPlace();\n      const label = view?.label || view?.name;')
    js = _replace(js, "      write($('place-name'), label || 'Set location');",
                  "      write($('place-name'), view?.name || 'Set location');")
    js = _replace(js, '''      weatherRequest?.abort();
      home = next;
      if (explicit) explored = null;
      sun = null;
      renderHome();
      renderGlobe(explicit);
      paintSun(new Date());''', '''      home = next;
      if (explicit) explored = null;
      renderGlobe(explicit);
      if (!explored) switchForecast();
    }

    function switchForecast() {
      weatherRequest?.abort();
      weatherRequest = null;
      sun = null;
      renderHome();
      paintSun(new Date());''')
    js = _replace(js, '''      if (!home) { openLocation(); return; }
      explored = null;
      renderGlobe(true);''', '''      if (!home) {
        if (explored) { explored = null; renderGlobe(true); switchForecast(); }
        openLocation();
        return;
      }
      const returning = explored !== null;
      explored = null;
      renderGlobe(true);
      if (returning) switchForecast();''')
    js = _replace(js, '      if (!home || (!force', '      if (!displayedPlace() || (!force')
    js = _replace(js, '      const target = home;', '      const target = displayedPlace();')
    js = _replace(js, '      const zone = home?.zone || deviceZone();\n      if (home) {', '      const view = displayedPlace();\n      const zone = view?.zone || deviceZone();\n      if (view) {')
    js = _replace(js, '{ ...home, zone }', '{ ...view, zone }')
    js = _replace(js, '    let home = readManualHome();', '''    const locationModeKey = 'home-new-tab.location-mode.v1';
    const deviceHomeKey = 'home-new-tab.device-home.v1';
    function locationMode(value) {
      try {
        if (value) localStorage.setItem(locationModeKey, value);
        else return localStorage.getItem(locationModeKey);
      } catch { /* Storage may not be available. */ }
    }

    function readDeviceHome() {
      if (locationMode() !== 'device') return null;
      try {
        const saved = JSON.parse(localStorage.getItem(deviceHomeKey));
        if (saved && typeof saved.name === 'string' && saved.name.trim() && validCoordinates(saved.lat, saved.lon)) {
          const name = saved.name === 'Current location' ? 'Last known location' : saved.name;
          return { name, lat: saved.lat, lon: saved.lon, zone: null, gps: true };
        }
      } catch { /* Storage may be unavailable or contain invalid data. */ }
      return null;
    }

    function saveDeviceHome({ name, lat, lon }) {
      try { localStorage.setItem(deviceHomeKey, JSON.stringify({ name, lat, lon })); } catch { /* Keep the in-page location. */ }
    }

    let home = readDeviceHome() || readManualHome();''')
    js = _replace(js, '    function locateDevice(current, success, failure) {',
                  '    function locateDevice(current, success, failure, precise = false) {')
    js = _replace(js, '''        navigator.geolocation.getCurrentPosition(({ coords }) => {
          if (!current()) return;
          if (!validCoordinates(coords.latitude, coords.longitude)) { failure(); return; }
          success({ name: 'Current location', lat: Number(coords.latitude.toFixed(2)),
            lon: Number(coords.longitude.toFixed(2)), zone: null, gps: true });
        }, failure, { enableHighAccuracy: false, timeout: 10_000, maximumAge: 5 * minute });''', '''        navigator.geolocation.getCurrentPosition(async ({ coords }) => {
          if (!current()) return;
          if (!validCoordinates(coords.latitude, coords.longitude)) { failure(); return; }
          const {latitude, longitude, accuracy} = coords;
          const city = await window.HomeNearbyCity?.(latitude, longitude, accuracy);
          if (!current()) return;
          const name = city ? `Near ${city}` : accuracy > 8_000 ? 'Approximate location' : 'Current location';
          success({ name, lat: Number(latitude.toFixed(2)), lon: Number(longitude.toFixed(2)), zone: null, gps: true });
        }, failure, { enableHighAccuracy: precise, timeout: 12_000, maximumAge: precise ? 0 : 2 * minute });''')
    js = _replace(js, '    async function locateIfAllowed() {\n      const version', '''    async function locateIfAllowed() {
      const mode = locationMode();
      // Chrome grants the required extension permission at install. Do not
      // read the device location until the user enables it inside Home.
      if (mode === 'manual' || (isExtension && mode !== 'device')) return;
      const version''')
    js = _replace(js, '      if (granted && current()) locateDevice(current, (next) => selectHome(next), () => {});', '''      if (granted && current()) locateDevice(current, (next) => {
        if (locationMode() !== mode) return;
        if (mode === 'device') saveDeviceHome(next);
        if (home?.gps && home.lat === next.lat && home.lon === next.lon && home.name === next.name) return;
        selectHome(next);
      }, () => {});''')
    js = _replace(js, '''      if (isExtension) {
        try {
          const granted = await globalThis.chrome.permissions.request(geolocationPermission);
          if (!current()) return;
          if (!granted) { failure({ code: 1 }); return; }
        } catch { failure(); return; }
      }
      locateDevice(current, (next) => {''', '''      locateDevice(current, (next) => {''')
    js = _replace(js, '        selectHome(next, true);\n        closeLocation();\n      }, failure);',
                  "        locationMode('device');\n        saveDeviceHome(next);\n        selectHome(next, true);\n        closeLocation();\n      }, failure, true);")
    return _replace(js, '            saveManualHome(manual);', '''            locationMode('manual');
            try { localStorage.removeItem(deviceHomeKey); } catch { /* Storage may not be available. */ }
            saveManualHome(manual);''')


HOME_STATE = """    function readManualHome() {
      for (const key of [storageKey, legacyStorageKey]) {
        try {
          const saved = JSON.parse(localStorage.getItem(key));
          // Legacy clock picks had no label; only a city search supplied one.
          if (saved && saved.gps !== true && typeof saved.name === 'string' && saved.name.trim() &&
              typeof saved.label === 'string' && saved.label.trim() &&
              validCoordinates(saved.lat, saved.lon) && validZone(saved.zone)) return saved;
        } catch { /* Storage can be disabled or contain invalid data. */ }
      }
      return null;
    }

    let home = readManualHome();
    let explored = null;
    const defaultView = cities.find((city) => Intl.DateTimeFormat('en', { timeZone: city.zone })
      .resolvedOptions().timeZone === deviceZone()) || madrid;

    function saveManualHome(manual) {
      try { localStorage.setItem(storageKey, JSON.stringify(manual)); } catch { /* Keep the in-page selection. */ }
    }

"""

RENDER_HOME = """    function renderHome() {
      const label = home?.label || home?.name;
      write($('place-name'), label || 'Set location');
      $('weather-place').setAttribute('aria-label', label ? `Change weather location: ${label}` : 'Set weather location');
      write($('weather-condition'), label ? '' : 'Location not set');
    }

    function renderGlobe(force = false) {
      const selected = explored || home;
      const match = (location) => location && cities.find((city) => city.name === location.name &&
        Math.abs(city.lat - location.lat) < 0.1 && Math.abs(city.lon - location.lon) < 0.1);
      const selectedCity = match(selected);
      for (const { city, button } of clocks) {
        button.classList.toggle('active', city === selectedCity);
        button.setAttribute('aria-pressed', String(city === selectedCity));
      }
      const pins = home && !match(home) ? [...cities, home] : cities;
      window.AlmanacGlobe?.setPlace(selected || defaultView, pins);
      if (force) window.AlmanacGlobe?.centerPlace?.();
    }

    function selectHome(next, explicit = false) {
      weatherRequest?.abort();
      home = next;
      if (explicit) explored = null;
      sun = null;
      renderHome();
      renderGlobe(explicit);
      paintSun(new Date());
      write($('weather-temp'), '—');
      weatherIcon.replaceChildren();
      refreshWeather(true);
    }

"""

GEOLOCATION = """    const geolocationPermission = { permissions: ['geolocation'] };
    const isExtension = Boolean(globalThis.chrome?.runtime?.id);

    function locateDevice(current, success, failure) {
      try {
        if (!navigator.geolocation) { failure(); return; }
        navigator.geolocation.getCurrentPosition(({ coords }) => {
          if (!current()) return;
          if (!validCoordinates(coords.latitude, coords.longitude)) { failure(); return; }
          success({ name: 'Current location', lat: Number(coords.latitude.toFixed(2)),
            lon: Number(coords.longitude.toFixed(2)), zone: null, gps: true });
        }, failure, { enableHighAccuracy: false, timeout: 10_000, maximumAge: 5 * minute });
      } catch { failure(); }
    }

    async function locateIfAllowed() {
      const version = locationVersion;
      const current = () => version === locationVersion && !dialog.open;
      let granted;
      try {
        granted = isExtension ? await globalThis.chrome.permissions?.contains(geolocationPermission) :
          (await navigator.permissions?.query({ name: 'geolocation' }))?.state === 'granted';
      } catch { return; }
      if (granted && current()) locateDevice(current, (next) => selectHome(next), () => {});
    }

    locate.addEventListener('click', async () => {
      const version = resetLocationWork();
      const current = () => version === locationVersion && dialog.open;
      if (!current()) return;
      results.replaceChildren();
      locate.disabled = true;
      write(status, 'Finding your location…');
      const failure = (error) => {
        if (!current()) return;
        locate.disabled = false;
        write(status, error?.code === 1 ? 'Location permission denied. Search for a city.' :
          'Location unavailable. Search for a city.');
      };
      if (isExtension) {
        try {
          const granted = await globalThis.chrome.permissions.request(geolocationPermission);
          if (!current()) return;
          if (!granted) { failure({ code: 1 }); return; }
        } catch { failure(); return; }
      }
      locateDevice(current, (next) => {
        selectHome(next, true);
        closeLocation();
      }, failure);
    });

"""
