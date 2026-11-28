"""Show progress along the daylight or overnight arc."""


def solar_cursor(js):
    start = js.index('    function paintSun(now) {')
    end = js.index('    function paintMoon(now) {', start)
    anchor = '      return { civilDay, rise, set, windows };'
    if js.count(anchor) != 1:
        raise ValueError('Expected one solar-day result')
    js = js[:start] + CURSOR + js[end:]
    state = "    const marker = $('sun-marker');\n"
    if js.count(state) != 1:
        raise ValueError('Expected one sun marker')
    js = js.replace(state, state + "    const sunTurn = { shown: null, place: null, route: null, frame: 0 };\n")
    return js.replace(anchor, '''      // Start each night at a sunset and pair it with the next nearby sunrise.
      const nightWindows = [event(begin, -1, -1), set]
        .filter((sunset) => sunset !== null)
        .map((sunset) => [sunset, event(sunset, +1, 1)]);
      return { civilDay, rise, set, windows, nightWindows };''')


CURSOR = '''    function paintSun(now) {
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

'''
