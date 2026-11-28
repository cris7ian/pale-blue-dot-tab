(() => {
  'use strict';

  function start() {
    const $ = (id) => document.getElementById(id);
    const svgNS = 'http://www.w3.org/2000/svg';
    const storageKey = 'local-almanac.manual-home.v1';
    const legacyStorageKey = 'local-almanac.place.v1';
    const minute = 60_000;
    const day = 24 * 60 * minute;
    const defaultCities = [
      { name: 'Los Angeles', lat: 34.05, lon: -118.24, zone: 'America/Los_Angeles' },
      { name: 'New York', lat: 40.71, lon: -74.01, zone: 'America/New_York' },
      { name: 'Caracas', lat: 10.48, lon: -66.88, zone: 'America/Caracas' },
      { name: 'London', lat: 51.51, lon: -0.13, zone: 'Europe/London' },
      { name: 'Madrid', lat: 40.42, lon: -3.70, zone: 'Europe/Madrid' },
      { name: 'Dubai', lat: 25.20, lon: 55.27, zone: 'Asia/Dubai' },
      { name: 'Tokyo', lat: 35.68, lon: 139.69, zone: 'Asia/Tokyo' },
      { name: 'Sydney', lat: -33.87, lon: 151.21, zone: 'Australia/Sydney' },
    ];
    let cities = defaultCities;
    const madrid = defaultCities.find((city) => city.name === 'Madrid');
    const dialog = $('location-dialog');
    const query = $('city-query');
    const results = $('city-results');
    const status = $('location-status');
    const locate = $('locate');
    const weatherIcon = $('weather-icon');
    const marker = $('sun-marker');
    const sunTurn = { shown: null, place: null, route: null, frame: 0 };
    const formatterCache = new Map();
    let weatherRequest;
    let weatherDue = 0;
    let locationRequest;
    let locationVersion = 0;
    let sun;
    let moonMinute;
    const moonTurn = { current: null, frame: 0, place: null, sky: null, craters: null, surface: null, width: 0, colors: null };
    const moonGrain = new Map();
    const MOON_COLORS = {
      water: '#e2e2e2', land: '#bdbdbd', coast: '#747474',
      night: 'rgba(18,18,18,.52)', edge: '#525252',
    };
    // How much land color each traced depth adds, from the shore to the deep sea. Stacked,
    // they fade every mare in from its edge instead of drawing a coastline.
    const MOON_DEPTHS = [0.35, 0.45, 0.55, 0.65];

    function formatter(zone, options) {
      const key = JSON.stringify([zone, options]);
      if (!formatterCache.has(key)) {
        formatterCache.set(key, new Intl.DateTimeFormat('en-GB', { ...options, timeZone: zone }));
      }
      return formatterCache.get(key);
    }

    const timeOptions = { hour: '2-digit', minute: '2-digit', hourCycle: 'h12' };
    const dateOptions = { year: 'numeric', month: '2-digit', day: '2-digit' };
    const deviceZone = () => Intl.DateTimeFormat().resolvedOptions().timeZone;
    const time = (instant, zone) => clockText(parts(instant, zone, timeOptions));
    const clockText = ({hour, minute, dayPeriod}) => `${hour}:${minute} ${dayPeriod.toUpperCase()}`;
    function paintTime(node, value) {
      const [clock, period] = value.split(' ');
      if (node.dataset.value === value) return;
      node.dataset.value = value;
      node.replaceChildren(document.createTextNode(clock), ...(period ? [document.createTextNode(' '), html('span', 'meridiem', period)] : []));
      if (period) scanNumber(node);
    }
    const parts = (instant, zone, options) => Object.fromEntries(
      formatter(zone, options).formatToParts(instant).map(({ type, value }) => [type, value]),
    );
    const write = (node, text) => { if (node.textContent !== text) node.textContent = text; };

    function validZone(zone) {
      if (typeof zone !== 'string' || !zone) return false;
      try {
        formatter(zone, timeOptions);
        return true;
      } catch {
        return false;
      }
    }

    function validCoordinates(lat, lon) {
      return Number.isFinite(lat) && Math.abs(lat) <= 90 && Number.isFinite(lon) && Math.abs(lon) <= 180;
    }

    function readManualHome() {
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

    const locationModeKey = 'home-new-tab.location-mode.v1';
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

    let home = readDeviceHome() || readManualHome();
    let explored = null;
    const displayedPlace = () => explored || home;
    const defaultView = cities.find((city) => Intl.DateTimeFormat('en', { timeZone: city.zone })
      .resolvedOptions().timeZone === deviceZone()) || madrid;

    function saveManualHome(manual) {
      try { localStorage.setItem(storageKey, JSON.stringify(manual)); } catch { /* Keep the in-page selection. */ }
    }

    function html(tag, className, text) {
      const element = document.createElement(tag);
      if (className) element.className = className;
      if (text !== undefined) element.textContent = text;
      return element;
    }

    function svg(tag, attributes) {
      const element = document.createElementNS(svgNS, tag);
      for (const [name, value] of Object.entries(attributes)) element.setAttribute(name, value);
      return element;
    }

    function createClock(city) {
      const button = html('button', 'clock');
      button.type = 'button';
      const clockTime = html('span', 'clock-time');
      const offset = html('span', 'clock-offset');
      button.append(html('span', 'clock-city', city.name), clockTime, offset);
      button.addEventListener('click', () => {
        explored = city;
        renderGlobe(true);
        switchForecast();
      });
      if (city.label) button.title = city.label;
      return { city, button, clockTime, offset };
    }

    let clocks;

    function renderHome() {
      const view = displayedPlace();
      const label = view?.label || view?.name;
      write($('place-name'), view?.name || 'Set location');
      $('weather-place').setAttribute('aria-label', label ? `Change weather location: ${label}` : 'Set weather location');
      write($('weather-condition'), label ? '' : 'Location not set');
    }

    function renderGlobe(force = false) {
      const selected = explored || home;
      const match = (location) => location && cities.find((city) => sameCity(city, location));
      const selectedCity = match(selected);
      for (const { city, button } of clocks) {
        button.classList.toggle('active', city === selectedCity);
        button.setAttribute('aria-pressed', String(city === selectedCity));
      }
      const pins = home && !match(home) ? [...cities, home] : cities;
      window.AlmanacGlobe?.setPlace(selected || defaultView, pins);
      paintMoon(new Date());
      if (force) window.AlmanacGlobe?.centerPlace?.();
    }

    function selectHome(next, explicit = false) {
      home = next;
      if (explicit) explored = null;
      renderGlobe(explicit);
      if (!explored) switchForecast();
    }

    function switchForecast() {
      weatherRequest?.abort();
      weatherRequest = null;
      sun = null;
      renderHome();
      paintSun(new Date());
      paintTemperature('—');
      weatherIcon.replaceChildren();
      refreshWeather(true);
    }

    const conditions = {
      0: ['Clear sky', 'clear'], 1: ['Mainly clear', 'partly'], 2: ['Partly cloudy', 'partly'],
      3: ['Overcast', 'cloud'], 45: ['Fog', 'fog'], 48: ['Depositing rime fog', 'fog'],
      51: ['Light drizzle', 'drizzle'], 53: ['Moderate drizzle', 'drizzle'], 55: ['Dense drizzle', 'drizzle'],
      56: ['Light freezing drizzle', 'sleet'], 57: ['Dense freezing drizzle', 'sleet'],
      61: ['Slight rain', 'rain'], 63: ['Moderate rain', 'rain'], 65: ['Heavy rain', 'rain'],
      66: ['Light freezing rain', 'sleet'], 67: ['Heavy freezing rain', 'sleet'],
      71: ['Slight snowfall', 'snow'], 73: ['Moderate snowfall', 'snow'], 75: ['Heavy snowfall', 'snow'],
      77: ['Snow grains', 'snow'], 80: ['Slight rain showers', 'rain'],
      81: ['Moderate rain showers', 'rain'], 82: ['Violent rain showers', 'rain'],
      85: ['Slight snow showers', 'snow'], 86: ['Heavy snow showers', 'snow'],
      95: ['Thunderstorm', 'storm'], 96: ['Thunderstorm with slight hail', 'storm'],
      99: ['Thunderstorm with heavy hail', 'storm'],
    };

    function drawWeather(kind, isDay) {
      const sunGlyph = 'M24 12V7m0 34v-5M12 24H7m34 0h-5M15.5 15.5 12 12m24 24-3.5-3.5m0-17 3.5-3.5M12 36l3.5-3.5 M24 16a8 8 0 1 1 0 16 8 8 0 1 1 0-16';
      const moonGlyph = 'M29 7a17 17 0 1 0 12 23A15 15 0 0 1 29 7Z';
      const cloud = 'M12 32a6.5 6.5 0 0 1-.5-13A11 11 0 0 1 33 18a7 7 0 1 1 1 14Z';
      const partlyCloud = 'M11 37a6 6 0 0 1-.5-12A9 9 0 0 1 28 24a6.5 6.5 0 1 1 2 13Z';
      const accents = {
        fog: 'M9 37h30M14 42h20', drizzle: 'M15 37l-1 2m10-2-1 2m10-2-1 2',
        rain: 'M15 36l-3 6m12-6-3 6m12-6-3 6', sleet: 'M15 36l-3 6m12-3h5m-2.5-2.5v5m8-5.5-3 6',
        snow: 'M12 39h6m-3-3v6m-2-5 4 4m0-4-4 4m10 0h6m-3-3v6m-2-5 4 4m0-4-4 4m9-4h6m-3-3v6m-2-5 4 4m0-4-4 4',
        storm: 'M24 32l-5 6h8l-5 7',
      };
      let shape;
      if (kind === 'clear') shape = isDay ? sunGlyph : moonGlyph;
      else if (kind === 'partly') {
        const behind = isDay ? 'M25 13a7 7 0 0 1 13 5m-7-9V6m9 6 3-2m-1 11h3' : 'M25 13a10 10 0 0 1 8-6 9 9 0 0 0 9 11 11 11 0 0 1-4 4';
        shape = `${behind} ${partlyCloud}`;
      } else if (kind) shape = `${cloud} ${accents[kind] || ''}`;
      weatherIcon.replaceChildren(...(shape ? [svg('path', {
        d: shape, fill: 'none', stroke: 'currentColor', 'stroke-width': 1.5,
        'stroke-linecap': 'round', 'stroke-linejoin': 'round',
      })] : []));
    }

    async function fetchJSON(url, controller) {
      const timeout = setTimeout(() => controller.abort(), 10_000);
      try {
        const response = await fetch(url, { signal: controller.signal, credentials: 'omit', referrerPolicy: 'no-referrer' });
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return await response.json();
      } finally {
        clearTimeout(timeout);
      }
    }

    function scanNumber(node) {
      if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
      node.animate(
        [{ clipPath: 'inset(-20% 85% -20% 0)' }, { clipPath: 'inset(-20% 0 -20% 0)' }],
        { duration: 180, easing: 'steps(5)' },
      );
    }

    function paintTemperature(value, loading = false) {
      const node = $('weather-temp');
      const changed = node.textContent !== value;
      write(node, value);
      node.hidden = loading;
      $('weather-loading').hidden = !loading;
      $('weather-unit').hidden = loading;
      if (changed && value !== '—') scanNumber(node);
    }

    async function refreshWeather(force = false) {
      if (!displayedPlace() || (!force && (weatherRequest || Date.now() < weatherDue || document.hidden))) return;
      const controller = new AbortController();
      const target = displayedPlace();
      if ($('weather-temp').textContent === '—') {
        paintTemperature('—', true);
        write($('weather-condition'), 'Loading weather…');
      }
      weatherRequest = controller;
      const url = new URL('https://api.open-meteo.com/v1/forecast');
      url.search = new URLSearchParams({
        latitude: target.lat.toFixed(2), longitude: target.lon.toFixed(2),
        current: 'temperature_2m,weather_code,is_day', temperature_unit: 'celsius', timezone: 'auto',
      });
      try {
        const data = await fetchJSON(url, controller);
        if (weatherRequest !== controller) return;
        if (target.gps && validZone(data.timezone) && data.timezone !== target.zone) {
          target.zone = data.timezone;
          sun = null;
          paintSun(new Date());
        }
        const current = data.current;
        if (!current || !Number.isFinite(current.temperature_2m)) throw new Error('Missing current weather');
        const [description, kind] = conditions[current.weather_code] || ['Condition unavailable', null];
        paintTemperature(String(Math.round(current.temperature_2m)));
        write($('weather-condition'), description);
        drawWeather(kind, current.is_day !== 0);
        weatherDue = Date.now() + 15 * minute;
      } catch {
        if (weatherRequest !== controller) return;
        paintTemperature('—');
        write($('weather-condition'), 'Weather unavailable');
        drawWeather(null);
        weatherDue = Date.now() + minute;
      } finally {
        if (weatherRequest === controller) weatherRequest = null;
      }
    }

    function resetLocationWork() {
      locationVersion += 1;
      locationRequest?.abort();
      locationRequest = null;
      locate.disabled = false;
      return locationVersion;
    }

    function closeLocation() {
      resetLocationWork();
      dialog.close();
    }

    function openLocation(forClock = false) {
      if (dialog.open) return;
      resetLocationWork();
      addingClock = forClock;
      write($('location-title'), forClock ? 'Add city clock' : 'Location');
      $('location-close').setAttribute('aria-label', forClock ? 'Close city clock search' : 'Close location selector');
      locate.hidden = forClock;
      query.value = '';
      results.replaceChildren();
      write(status, '');
      dialog.showModal();
      query.focus();
    }

    $('weather-place').addEventListener('click', () => openLocation());
    function returnHome(event) {
      event.preventDefault();
      event.stopImmediatePropagation();
      if (!home) {
        if (explored) { explored = null; renderGlobe(true); switchForecast(); }
        openLocation();
        return;
      }
      const returning = explored !== null;
      explored = null;
      renderGlobe(true);
      if (returning) switchForecast();
    }
    $('globe-home')?.addEventListener('click', returnHome, { capture: true });
    $('globe')?.addEventListener('keydown', (event) => {
      if (event.key === 'Home' && !event.altKey && !event.ctrlKey && !event.metaKey) returnHome(event);
    }, { capture: true });
    $('location-close').addEventListener('click', closeLocation);
    dialog.addEventListener('close', () => { if (!dialog.open) resetLocationWork(); });
    query.addEventListener('input', () => {
      resetLocationWork();
      results.replaceChildren();
      write(status, '');
    });

    const geolocationPermission = { permissions: ['geolocation'] };
    const isExtension = Boolean(globalThis.chrome?.runtime?.id);

    function locateDevice(current, success, failure, precise = false) {
      try {
        if (!navigator.geolocation) { failure(); return; }
        navigator.geolocation.getCurrentPosition(async ({ coords }) => {
          if (!current()) return;
          if (!validCoordinates(coords.latitude, coords.longitude)) { failure(); return; }
          const {latitude, longitude, accuracy} = coords;
          const city = await window.HomeNearbyCity?.(latitude, longitude, accuracy);
          if (!current()) return;
          const name = city ? `Near ${city}` : accuracy > 8_000 ? 'Approximate location' : 'Current location';
          success({ name, lat: Number(latitude.toFixed(2)), lon: Number(longitude.toFixed(2)), zone: null, gps: true });
        }, failure, { enableHighAccuracy: precise, timeout: 12_000, maximumAge: precise ? 0 : 2 * minute });
      } catch { failure(); }
    }

    async function locateIfAllowed() {
      const mode = locationMode();
      // Chrome grants the required extension permission at install. Do not
      // read the device location until the user enables it inside Home.
      if (mode === 'manual' || (isExtension && mode !== 'device')) return;
      const version = locationVersion;
      const current = () => version === locationVersion && !dialog.open;
      let granted;
      try {
        granted = isExtension ? await globalThis.chrome.permissions?.contains(geolocationPermission) :
          (await navigator.permissions?.query({ name: 'geolocation' }))?.state === 'granted';
      } catch { return; }
      if (granted && current()) locateDevice(current, (next) => {
        if (locationMode() !== mode) return;
        if (mode === 'device') saveDeviceHome(next);
        if (home?.gps && home.lat === next.lat && home.lon === next.lon && home.name === next.name) return;
        selectHome(next);
      }, () => {});
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
      locateDevice(current, (next) => {
        locationMode('device');
        saveDeviceHome(next);
        selectHome(next, true);
        closeLocation();
      }, failure, true);
    });

    $('city-search').addEventListener('submit', async (event) => {
      event.preventDefault();
      const version = resetLocationWork();
      results.replaceChildren();
      const name = query.value.trim();
      if (name.length < 2) {
        write(status, 'Enter at least two characters.');
        return;
      }
      write(status, 'Searching…');
      const url = new URL('https://geocoding-api.open-meteo.com/v1/search');
      url.search = new URLSearchParams({ name, count: '8', language: 'en', format: 'json' });
      const controller = new AbortController();
      locationRequest = controller;
      const current = () => version === locationVersion && dialog.open;
      try {
        const data = await fetchJSON(url, controller);
        if (!current()) return;
        const matches = (data.results || []).filter((item) => typeof item.name === 'string' &&
          validCoordinates(item.latitude, item.longitude) && validZone(item.timezone));
        const labels = matches.map((item) => [item.name, item.admin1, item.country || item.country_code]);
        const baseLabels = labels.map(placeLabel);
        for (const [index, item] of matches.entries()) {
          const label = baseLabels.some((value, i) => i !== index && value === baseLabels[index]) ?
            placeLabel([item.name, item.admin2, ...labels[index].slice(1)]) : baseLabels[index];
          const button = html('button', '', addingClock ? `Add ${label}` : label);
          button.type = 'button';
          button.addEventListener('click', async () => {
            if (!current()) return;
            const manual = { name: item.name, label, lat: item.latitude, lon: item.longitude, zone: item.timezone };
            if (addingClock) {
              const added = await editClocks(() => addClock(manual));
              if (!current()) return;
              if (added) closeLocation();
              else write(status, `${label} is already in your city clocks.`);
              return;
            }
            locationMode('manual');
            try { localStorage.removeItem(deviceHomeKey); } catch { /* Storage may not be available. */ }
            saveManualHome(manual);
            selectHome(manual, true);
            closeLocation();
          });
          const row = html('li');
          row.append(button);
          results.append(row);
        }
        write(status, matches.length ? '' : 'No cities found.');
      } catch {
        if (current()) write(status, 'City search unavailable. Try again.');
      } finally {
        if (locationRequest === controller) locationRequest = null;
      }
    });

    function placeLabel(parts) {
      return [...new Set(parts.filter(Boolean))].join(', ');
    }

    function localDay(instant, zone) {
      const { year, month, day: date } = parts(instant, zone, dateOptions);
      return Date.UTC(Number(year), Number(month) - 1, Number(date));
    }

    function startOfDay(civilDay, zone) {
      // Find the first instant in this civil date without assuming a fixed UTC offset.
      let low = civilDay - day;
      let high = civilDay + day;
      while (high - low > 1) {
        const middle = Math.floor((low + high) / 2);
        if (localDay(middle, zone) < civilDay) low = middle;
        else high = middle;
      }
      return high;
    }

    function sunForDay(civilDay, location) {
      const begin = startOfDay(civilDay, location.zone);
      const end = startOfDay(civilDay + day, location.zone);
      const observer = new Astronomy.Observer(location.lat, location.lon, 0);
      function event(start, direction, limitDays) {
        return Astronomy.SearchRiseSet(Astronomy.Body.Sun, observer, direction, new Date(start), limitDays)
          ?.date.getTime() ?? null;
      }
      function inDay(direction) {
        const crossing = event(begin, direction, (end - begin) / day);
        return crossing !== null && crossing >= begin && crossing < end ? crossing : null;
      }
      const rise = inDay(+1);
      const set = inDay(-1);
      const windows = [];
      if (rise !== null && set !== null && rise < set) windows.push([rise, set]);
      else {
        // Daylight can cross civil midnight. Polar days with no nearby pair have no marker.
        if (set !== null) windows.push([event(set, +1, -1), set]);
        if (rise !== null) windows.push([rise, event(rise, -1, 1)]);
      }
      // Start each night at a sunset and pair it with the next nearby sunrise.
      const nightWindows = [event(begin, -1, -1), set]
        .filter((sunset) => sunset !== null)
        .map((sunset) => [sunset, event(sunset, +1, 1)]);
      return { civilDay, rise, set, windows, nightWindows };
    }

    function paintSun(now) {
      const view = displayedPlace();
      const zone = view?.zone || deviceZone();
      if (view) {
        const civilDay = localDay(now, zone);
        if (!sun || sun.civilDay !== civilDay || sun.zone !== zone) {
          sun = { ...sunForDay(civilDay, { ...view, zone }), zone };
        }
      }
      const ms = now.getTime();
      const contains = ([start, end]) => start !== null && end !== null && start <= ms && ms < end;
      const daylight = sun?.windows.find(contains);
      const night = daylight ? null : sun?.nightWindows.find(contains);
      const label = instant => instant == null ? '—' : time(instant, zone);
      paintTime($('sunrise'), label(night ? night[1] : sun?.rise));
      paintTime($('sunset'), label(night ? night[0] : sun?.set));

      const interval = daylight || night;
      const caption = $('night-progress');
      if (!interval) {
        cancelAnimationFrame(sunTurn.frame);
        Object.assign(sunTurn, { shown: null, route: null });
        marker.setAttribute('visibility', 'hidden');
        marker.removeAttribute('data-state');
        write(caption, sun ? 'No complete solar cycle nearby' : '');
        return;
      }
      const [start, end] = interval;
      const progress = (ms - start) / (end - start);
      showCursor(progress, night ? 'night' : 'day', view);
      const remaining = Math.ceil((end - ms) / minute);
      const hours = Math.floor(remaining / 60);
      const minutes = remaining % 60;
      write(caption, night ? `${hours ? `${hours}h ` : ''}${minutes}m to sunrise` : '');
    }

    // A new place sends the sun or Moon along the arc to its spot, beside the globe's flight.
    // Crossing between day and night, it sets at one end and the other rises at the opposite
    // end, whichever way round is shorter. Clock ticks keep moving it in place.
    function showCursor(t, state, view) {
      const target = { t, state };
      const moved = view !== sunTurn.place;
      sunTurn.place = view;
      if (sunTurn.route && !moved) {
        sunTurn.route.to = target;
        return;
      }
      const from = sunTurn.shown;
      if (!moved || !from || matchMedia('(prefers-reduced-motion: reduce)').matches) {
        cancelAnimationFrame(sunTurn.frame);
        sunTurn.route = null;
        placeCursor(t, state);
        return;
      }
      cancelAnimationFrame(sunTurn.frame);
      const across = from.state !== state;
      const forward = across && (1 - from.t) + t <= from.t + (1 - t);
      const route = sunTurn.route = { from, to: target, across, forward, start: performance.now() };
      const legs = () => !across ? [[from.state, from.t, route.to.t]]
        : forward ? [[from.state, from.t, 1], [route.to.state, 0, route.to.t]]
          : [[from.state, from.t, 0], [route.to.state, 1, route.to.t]];
      const length = legs().reduce((sum, [, a, b]) => sum + Math.abs(b - a), 0);
      if (length < 0.002) {
        sunTurn.route = null;
        placeCursor(t, state);
        return;
      }
      const duration = 420 + 520 * Math.min(1, length);
      const step = (now) => {
        const progress = Math.max(0, Math.min(1, (now - route.start) / duration));
        const eased = progress < 0.5 ? 4 * progress ** 3 : 1 - (-2 * progress + 2) ** 3 / 2;
        const path = legs();
        let left = eased * path.reduce((sum, [, a, b]) => sum + Math.abs(b - a), 0);
        for (const [i, [glyph, a, b]] of path.entries()) {
          const span = Math.abs(b - a);
          if (left <= span || i === path.length - 1) {
            const at = a + Math.sign(b - a) * Math.min(left, span);
            // Near the horizon it sinks and fades, so the swap happens out of sight.
            const horizon = across ? (i === 0 ? span - left : left) : 1;
            placeCursor(at, glyph, Math.min(1, horizon / 0.09) ** 2);
            break;
          }
          left -= span;
        }
        if (progress < 1) {
          sunTurn.frame = requestAnimationFrame(step);
        } else {
          sunTurn.route = null;
          placeCursor(route.to.t, route.to.state);
        }
      };
      sunTurn.frame = requestAnimationFrame(step);
    }

    function placeCursor(t, state, fade = 1) {
      const x = 20 + 280 * t;
      const height = Math.max(17, 236 * t * (1 - t));
      const y = 78 - height + 14 * (1 - fade);
      marker.setAttribute('transform', `translate(${x.toFixed(2)} ${y.toFixed(2)})`);
      marker.setAttribute('data-state', state);
      if (fade < 1) marker.setAttribute('opacity', fade.toFixed(3));
      else marker.removeAttribute('opacity');
      marker.removeAttribute('visibility');
      sunTurn.shown = { t, state };
    }

    // Angles in degrees, measured from celestial north through east (Meeus, ch. 14 and 48).
    function moonTilt(now, view) {
      const observer = new Astronomy.Observer(view.lat, view.lon, 0);
      const moon = Astronomy.Equator(Astronomy.Body.Moon, now, observer, true, true);
      const sun = Astronomy.Equator(Astronomy.Body.Sun, now, observer, true, true);
      const rad = Math.PI / 180;
      const lat = view.lat * rad, dec = moon.dec * rad, sunDec = sun.dec * rad;
      const hour = Astronomy.HourAngle(Astronomy.Body.Moon, now, observer) * 15 * rad;
      const ra = (sun.ra - moon.ra) * 15 * rad;
      // Parallactic angle: where the observer's zenith lies on the Moon's disk.
      const zenith = Math.atan2(Math.sin(hour),
        Math.tan(lat) * Math.cos(dec) - Math.sin(dec) * Math.cos(hour)) / rad;
      // Position angle of the midpoint of the bright limb, which faces the Sun.
      const limb = Math.atan2(Math.cos(sunDec) * Math.sin(ra),
        Math.sin(sunDec) * Math.cos(dec) - Math.cos(sunDec) * Math.sin(dec) * Math.cos(ra)) / rad;
      return { zenith, limb };
    }

    // Position angle of the Moon's north pole on the sky (Meeus, ch. 53), within about ±25°.
    function moonAxis(now) {
      const pole = Astronomy.RotationAxis(Astronomy.Body.Moon, now);
      const moon = Astronomy.EquatorFromVector(Astronomy.GeoVector(Astronomy.Body.Moon, now, true));
      const rad = Math.PI / 180;
      const ra = (pole.ra - moon.ra) * 15 * rad, poleDec = pole.dec * rad, dec = moon.dec * rad;
      return Math.atan2(Math.cos(poleDec) * Math.sin(ra),
        Math.sin(poleDec) * Math.cos(dec) - Math.cos(poleDec) * Math.sin(dec) * Math.cos(ra)) / rad;
    }

    // The slowly changing view of the Moon: libration, axis tilt and phase angle.
    function moonSky(now) {
      return {
        libration: Astronomy.Libration(now),
        axis: moonAxis(now),
        phase: Astronomy.Illumination(Astronomy.Body.Moon, now).phase_angle,
      };
    }

    // Clockwise screen angles from straight up: `roll` turns lunar north, `light` points to the
    // bright limb. With a place, its zenith is up; without one, celestial north is up.
    function moonAngles(now, place, sky) {
      if (!place) return { roll: -sky.axis, light: -moonTilt(now, { lat: 0, lon: 0 }).limb };
      const { zenith, limb } = moonTilt(now, place);
      return { roll: zenith - sky.axis, light: zenith - limb };
    }

    // The globe's orthographic projection, centered on the sub-Earth point and turned by the
    // roll. Night is the hemisphere around the antisolar point, placed by the phase angle.
    function moonView(size, sky, { roll, light }) {
      const rad = Math.PI / 180;
      const projection = d3.geoOrthographic().clipAngle(90).precision(1)
        .translate([size / 2, size / 2]).scale(size * 49 / 128)
        .rotate([-sky.libration.elon, -sky.libration.elat, -roll]);
      const i = sky.phase * rad, bearing = light * rad;
      // The Sun's direction in view coordinates (east right, north up), then on the Moon.
      const view = [Math.atan2(Math.sin(i) * Math.sin(bearing), Math.cos(i)) / rad,
        Math.asin(Math.sin(i) * Math.cos(bearing)) / rad];
      const [lon, lat] = d3.geoRotation(projection.rotate()).invert(view);
      const night = d3.geoCircle().center([lon > 0 ? lon - 180 : lon + 180, -lat]).radius(90).precision(2)();
      return { projection, night };
    }

    function paintMoon(now) {
      const view = displayedPlace();
      const bucket = `${Math.floor(now / minute)} ${view?.lat} ${view?.lon}`;
      if (moonMinute === bucket) return;
      moonMinute = bucket;
      const angle = Astronomy.MoonPhase(now);
      const fraction = Math.max(0, Math.min(1, Astronomy.Illumination(Astronomy.Body.Moon, now).phase_fraction));
      let phase;
      if (angle < 6 || angle >= 354) phase = 'New Moon';
      else if (angle < 84) phase = 'Waxing Crescent';
      else if (angle < 96) phase = 'First Quarter';
      else if (angle < 174) phase = 'Waxing Gibbous';
      else if (angle < 186) phase = 'Full Moon';
      else if (angle < 264) phase = 'Waning Gibbous';
      else if (angle < 276) phase = 'Last Quarter';
      else phase = 'Waning Crescent';
      write($('moon-phase'), phase);
      write($('moon-percent'), `${Math.round(100 * fraction)}%`);

      // The sun cursor's night glyph. Limb is a semicircle; the projected terminator has
      // horizontal radius r × |1 − 2f|.
      const wax = angle < 180;
      const rx = 49 * Math.abs(1 - 2 * fraction);
      const sweep = Number(wax === (fraction >= 0.5));
      const terminator = rx < 0.0001 ? 'L 64 15' : `A ${rx.toFixed(5)} 49 0 0 ${sweep} 64 15`;
      $('moon-lit').setAttribute('d', `M 64 15 A 49 49 0 0 ${Number(wax)} 64 113 ${terminator} Z`);

      const sky = moonTurn.sky = moonSky(now);
      const from = moonTurn.place;
      moonTurn.place = view ? { lat: view.lat, lon: view.lon } : null;
      const moved = from && view && (from.lat !== view.lat || from.lon !== view.lon);
      if (moved) flyMoon(now, from, view, sky);
      else turnMoon(moonAngles(now, view, sky));
    }

    // Travel the globe's route to the new city and show the Moon as it looks from each point
    // on the way. The Moon follows the Earth: it sets off a beat later, eases more gently,
    // and settles after the globe has stopped.
    function flyMoon(now, from, to, sky) {
      cancelAnimationFrame(moonTurn.frame);
      const start = [from.lon, from.lat], end = [to.lon, to.lat];
      if (matchMedia('(prefers-reduced-motion: reduce)').matches || d3.geoDistance(start, end) < 0.009) {
        showMoonTurn(moonAngles(now, to, sky));
        return;
      }
      const distance = d3.geoDistance(start, end);
      let route = d3.geoInterpolate(start, end);
      if (distance > Math.PI - 1e-7) {
        // Antipodes have no unique shortest arc. Go east, as the globe does.
        const waypoint = [((from.lon + 270) % 360 + 360) % 360 - 180, 0];
        const first = d3.geoInterpolate(start, waypoint), second = d3.geoInterpolate(waypoint, end);
        route = (t) => t < 0.5 ? first(2 * t) : second(2 * t - 1);
      }
      const globe = 370 + 470 * distance / Math.PI;
      const begin = performance.now() + 120, duration = globe * 1.35 + 150;
      // Cubic ease-in-out: a softer start and longer settle than the globe's smoothstep.
      const ease = (t) => t < 0.5 ? 4 * t * t * t : 1 - (-2 * t + 2) ** 3 / 2;
      const step = (time) => {
        if (time < begin) { moonTurn.frame = requestAnimationFrame(step); return; }
        const t = Math.min(1, (time - begin) / duration);
        const [lon, lat] = t === 1 ? end : route(ease(t));
        showMoonTurn(moonAngles(now, { lat, lon }, sky));
        if (t < 1) moonTurn.frame = requestAnimationFrame(step);
      };
      moonTurn.frame = requestAnimationFrame(step);
    }

    function showMoonTurn(angles) {
      moonTurn.current = angles;
      drawMoon();
    }

    // The globe's grain (globe.js `ink`): a 4×4 Bayer dot every other CSS pixel, in an 8 px tile.
    function moonInk(context, color, threshold) {
      const key = `${color}:${threshold}`;
      if (moonGrain.has(key)) return moonGrain.get(key);
      const tile = document.createElement('canvas');
      tile.width = tile.height = 8;
      const pixels = tile.getContext('2d');
      pixels.fillStyle = color;
      [0, 8, 2, 10, 12, 4, 14, 6, 3, 11, 1, 9, 15, 7, 13, 5].forEach((value, i) => {
        if (value < threshold) pixels.fillRect((i % 4) * 2, Math.floor(i / 4) * 2, 1, 1);
      });
      const pattern = context.createPattern(tile, 'repeat');
      moonGrain.set(key, pattern);
      return pattern;
    }

    // Major craters as small circles on the sphere: bright rayed craters light, dark-floored
    // craters filled, and the great walled plains as faint rims.
    function moonCraters(craters) {
      return craters.map(([lon, lat, radius, look]) =>
        ({ look, shape: d3.geoCircle().center([lon, lat]).radius(radius).precision(10)() }));
    }

    // Paint the Moon in the globe's layers and theme colors: highlands as water, maria as land
    // in soft depths, the craters, the limb shading, then the dotted night.
    // The Moon redraws on every frame of a turn, alongside the globe, so the surface is projected
    // once per sky into Path2Ds, and size and theme colors are read only when they change.
    function drawMoon() {
      const canvas = $('moon-canvas'), data = window.AlmanacMoonData;
      const context = canvas?.getContext?.('2d');
      if (!context || !data || !moonTurn.current || !moonTurn.sky) return;
      const css = moonTurn.width ||= canvas.getBoundingClientRect().width;
      if (!css) return;
      const ratio = Math.min(3, devicePixelRatio || 1);
      const size = Math.round(css * ratio);
      if (canvas.width !== size) canvas.width = canvas.height = size;
      if (!moonTurn.colors) {
        const computed = getComputedStyle(canvas);
        moonTurn.colors = Object.fromEntries(Object.entries(MOON_COLORS).map(([key, color]) => [key,
          computed.getPropertyValue(`--globe-${key}`).trim() || color]));
      }
      const c = moonTurn.colors;
      const { roll } = moonTurn.current;
      const { projection, night } = moonView(css, moonTurn.sky, moonTurn.current);
      const shape = (geometry, view = projection) => {
        const outline = new Path2D();
        d3.geoPath(view, outline)(geometry);
        return outline;
      };
      // Roll only spins the face on screen, so the surface is projected once per sky, unrolled,
      // and each frame turns the canvas instead of projecting again.
      if (moonTurn.surface?.sky !== moonTurn.sky || moonTurn.surface.css !== css) {
        const flat = moonView(css, moonTurn.sky, { roll: 0, light: 0 }).projection;
        moonTurn.craters ??= moonCraters(data.craters);
        moonTurn.surface = {
          sky: moonTurn.sky, css,
          seas: data.maria.map((depth) => shape(depth, flat)),
          craters: moonTurn.craters.map(({ look, shape: circle }) => ({ look, path: shape(circle, flat) })),
        };
      }
      const center = css / 2, radius = css * 49 / 128;
      const spin = new DOMMatrix().translateSelf(center, center).rotateSelf(roll).translateSelf(-center, -center);
      // Grain stays square to the screen, like the globe's, while the face turns under it.
      const steady = (pattern) => { pattern.setTransform?.(spin.inverse()); return pattern; };
      const grain = document.documentElement.dataset.design === 'grid';
      const disc = () => { context.beginPath(); context.arc(center, center, radius, 0, 2 * Math.PI); };
      const fill = (outline, color) => { context.fillStyle = color; context.fill(outline); };
      const stroke = (outline, color, weight, alpha) => {
        context.strokeStyle = color;
        context.lineWidth = weight;
        context.globalAlpha = alpha;
        context.stroke(outline);
        context.globalAlpha = 1;
      };

      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      context.clearRect(0, 0, css, css);
      context.lineJoin = 'round';
      context.lineCap = 'round';
      context.save();
      disc();
      context.fillStyle = c.water;
      context.fill();
      context.clip();
      context.transform(spin.a, spin.b, spin.c, spin.d, spin.e, spin.f);
      moonTurn.surface.seas.forEach((sea, i) => {
        context.globalAlpha = MOON_DEPTHS[i];
        fill(sea, c.land);
        if (grain) fill(sea, steady(moonInk(context, 'rgba(0,0,0,.40)', 13)));
      });
      context.globalAlpha = 1;
      for (const { look, path: crater } of moonTurn.surface.craters) {
        if (look === 'bright') {
          fill(crater, 'rgba(255,255,255,.55)');
        } else if (look === 'dark') {
          context.globalAlpha = 0.8;
          fill(crater, c.land);
          context.globalAlpha = 1;
          stroke(crater, c.coast, 0.5, 0.3);
        } else {
          stroke(crater, c.coast, 0.55, 0.32);
        }
      }
      context.setTransform(ratio, 0, 0, ratio, 0, 0);
      if (grain) {
        context.fillStyle = moonInk(context, 'rgba(0,0,0,.12)', 4);
        context.fillRect(center - radius, center - radius, radius * 2, radius * 2);
      }
      const shading = context.createRadialGradient(center - radius * 0.18, center - radius * 0.24, radius * 0.12,
        center, center, radius);
      shading.addColorStop(0, 'rgba(255,255,255,.14)');
      shading.addColorStop(0.61, 'rgba(128,128,128,0)');
      shading.addColorStop(1, 'rgba(0,0,0,.17)');
      context.fillStyle = shading;
      context.fillRect(center - radius, center - radius, radius * 2, radius * 2);
      const dark = shape(night);
      fill(dark, c.night);
      if (grain) fill(dark, moonInk(context, 'rgba(255,255,255,.48)', 8));
      stroke(shape({ type: 'LineString', coordinates: night.coordinates[0] }), c.water, 0.75, 0.47);
      context.restore();
      disc();
      context.strokeStyle = c.edge;
      context.lineWidth = 1;
      context.stroke();
    }

    // Turn the short way with the globe's easing and pace: 370 ms plus up to 470 ms for a half turn.
    function turnMoon(target) {
      cancelAnimationFrame(moonTurn.frame);
      const from = moonTurn.current;
      const delta = (a, b) => ((b - a) % 360 + 540) % 360 - 180;
      const roll = from && delta(from.roll, target.roll);
      const light = from && delta(from.light, target.light);
      const span = from ? Math.max(Math.abs(roll), Math.abs(light)) : 0;
      if (span < 0.5 || matchMedia('(prefers-reduced-motion: reduce)').matches) {
        showMoonTurn(target);
        return;
      }
      const start = performance.now();
      const duration = 370 + 470 * span / 180;
      const step = (now) => {
        const t = Math.max(0, Math.min(1, (now - start) / duration));
        const eased = t * t * (3 - 2 * t);
        showMoonTurn({ roll: from.roll + roll * eased, light: from.light + light * eased });
        if (t < 1) moonTurn.frame = requestAnimationFrame(step);
      };
      moonTurn.frame = requestAnimationFrame(step);
    }

    if ($('moon-canvas')?.getContext) {
      new ResizeObserver(([entry]) => { moonTurn.width = entry.contentRect.width; drawMoon(); })
        .observe($('moon-canvas'));
      // Theme colors come from CSS, as on the globe.
      new MutationObserver(() => { moonTurn.colors = null; drawMoon(); })
        .observe(document.documentElement, { attributes: true, attributeFilter: ['data-theme'] });
    }

    function tick() {
      const now = new Date();
      const zone = deviceZone();
      const local = parts(now, zone, { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long',
        ...timeOptions, timeZoneName: 'short' });
      write($('day'), local.day);
      write($('month'), local.month);
      write($('weekday'), local.weekday);
      write($('year'), local.year);
      paintTime($('local-time'), clockText(local));
      write($('local-zone'), local.timeZoneName);
      paintClocks(now);
      paintSun(now);
      paintMoon(now);
    }

    function wake() {
      if (document.hidden) return;
      tick();
      refreshWeather();
    }

    const clockKey = 'home-new-tab.city-clocks.v1';
    const clockGrid = $('clocks');
    const clockList = $('city-clock-list');
    const addClockButton = $('add-city-clock');
    let addingClock = false;
    let clockStorageAvailable = true;

    function sameCity(first, second) {
      return first.name === second.name &&
        Math.abs(first.lat - second.lat) < 0.1 && Math.abs(first.lon - second.lon) < 0.1;
    }

    function readClocks() {
      if (!clockStorageAvailable) return cities;
      try {
        const saved = JSON.parse(localStorage.getItem(clockKey));
        if (Array.isArray(saved) && saved.every((city) => city &&
            typeof city.name === 'string' && city.name.trim() &&
            validCoordinates(city.lat, city.lon) && validZone(city.zone))) return saved;
      } catch { /* Use the current roster if storage is unavailable. */ return cities; }
      return defaultCities;
    }

    function renderClocks() {
      clocks = cities.map((city, rosterIndex) => {
        const row = html('li');
        const name = city.label || city.name;
        const remove = html('button', '', 'Remove');
        remove.type = 'button';
        remove.setAttribute('aria-label', `Remove ${name}`);
        remove.addEventListener('click', () => editClocks(() => {
          const index = clocks.findIndex((clock) => clock.row === row);
          const remaining = readClocks().filter((entry) => !sameCity(entry, city));
          saveClocks(remaining);
          const next = clockList.children[Math.min(index, remaining.length - 1)]?.lastElementChild;
          (next || addClockButton).focus();
        }));
        row.append(html('span', '', name), remove);
        return { ...createClock(city), row, rosterIndex };
      });
      clockGrid.style.setProperty('--clock-count', clocks.length);
      $('city-clocks-empty').hidden = cities.length > 0;
      paintClocks(new Date(), true);
    }

    function paintClocks(now, rosterChanged = false) {
      for (const clock of clocks) {
        const cityTime = parts(now, clock.city.zone, { ...timeOptions, timeZoneName: 'shortOffset' });
        // shortOffset in en-GB gives GMT, GMT+5:45, GMT-3:30, etc.
        const zone = cityTime.timeZoneName;
        const [hours, minutes = '0'] = zone.slice(4).split(':');
        clock.offsetMinutes = (zone[3] === '-' ? -1 : 1) * (Number(hours) * 60 + Number(minutes));
        paintTime(clock.clockTime, clockText(cityTime));
        write(clock.offset, zone.replace(/^GMT/, 'UTC'));
      }
      const compare = (a, b) => a.offsetMinutes - b.offsetMinutes || a.rosterIndex - b.rosterIndex;
      const outOfOrder = clocks.some((clock, index) => index > 0 && compare(clocks[index - 1], clock) > 0);
      if (!rosterChanged && !outOfOrder) return;
      if (outOfOrder) clocks.sort(compare);
      const focused = document.activeElement;
      clockGrid.replaceChildren(...clocks.map(({ button }) => button));
      clockList.replaceChildren(...clocks.map(({ row }) => row));
      if (clockGrid.contains(focused) || clockList.contains(focused)) focused.focus({ preventScroll: true });
    }

    function updateClocks(next) {
      cities = next;
      const removedExplored = explored && !cities.some((city) => sameCity(city, explored));
      if (removedExplored) explored = null;
      renderClocks();
      renderGlobe(Boolean(removedExplored));
      if (removedExplored) switchForecast();
      tick();
    }

    function saveClocks(next) {
      try {
        localStorage.setItem(clockKey, JSON.stringify(next));
      } catch { clockStorageAvailable = false; }
      updateClocks(next);
    }

    function editClocks(edit) {
      // Serialize edits across tabs where Web Locks are available.
      return navigator.locks ? navigator.locks.request(clockKey, edit) : edit();
    }

    function addClock(city) {
      const roster = readClocks();
      if (roster.some((entry) => sameCity(entry, city))) return false;
      saveClocks([...roster, city]);
      return true;
    }

    addClockButton.addEventListener('click', () => openLocation(true));
    window.addEventListener('storage', (event) => {
      if (event.storageArea === localStorage && (event.key === clockKey || event.key === null)) {
        updateClocks(readClocks());
      }
    });
    cities = readClocks();
    renderClocks();

    renderHome();
    renderGlobe();
    tick();
    refreshWeather(true);
    locateIfAllowed();
    setInterval(() => { if (!document.hidden) tick(); }, 1000);
    setInterval(() => refreshWeather(), minute);
    window.addEventListener('focus', wake);
    window.addEventListener('pageshow', wake);
    document.addEventListener('visibilitychange', wake);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
