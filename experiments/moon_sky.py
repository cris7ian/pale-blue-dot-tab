"""Draw the Moon as a map, like the globe, as it appears in the displayed city's sky.

The Moon turns with the city's horizon and the tilt of its axis, librates, follows the
globe's route between cities a beat behind it, and lights the hemisphere facing the Sun.
"""


def moon_sky(js):
    start = js.index('    function paintMoon(now) {')
    end = js.index('    function tick() {', start)
    js = js[:start] + PAINT_MOON + js[end:]
    js = _replace(js, '    let moonMinute;', '    let moonMinute;\n' + MOON_STATE)
    # Turn the Moon together with the globe when the displayed city changes, not on the next tick.
    setter = '      window.AlmanacGlobe?.setPlace(selected || defaultView, pins);'
    return _replace(js, setter, setter + '\n      paintMoon(new Date());')


def _replace(js, old, new):
    if js.count(old) != 1:
        raise ValueError(f'Expected one Moon anchor: {old}')
    return js.replace(old, new)


MOON_STATE = '''    const moonTurn = { current: null, frame: 0, place: null, sky: null, craters: null, surface: null, width: 0, colors: null };
    const moonGrain = new Map();
    const MOON_COLORS = {
      water: '#e2e2e2', land: '#bdbdbd', coast: '#747474',
      night: 'rgba(18,18,18,.52)', edge: '#525252',
    };
    // How much land color each traced depth adds, from the shore to the deep sea. Stacked,
    // they fade every mare in from its edge instead of drawing a coastline.
    const MOON_DEPTHS = [0.35, 0.45, 0.55, 0.65];'''


PAINT_MOON = r'''    // Angles in degrees, measured from celestial north through east (Meeus, ch. 14 and 48).
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

'''
