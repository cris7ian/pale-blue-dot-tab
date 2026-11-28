"""Build the three LAN previews and the unpacked Chrome extension. Does not touch production."""
from base64 import b64encode
import html
import json
from pathlib import Path
import re

from city_clocks import city_clocks
from local_weather import exploring_weather, local_weather
from moon_sky import moon_sky
from sun_cursor import solar_cursor

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
EXT = ROOT / 'extension'
PREVIEW = HERE / 'preview-local'
SRC = ROOT / 'src'
VENDOR = ROOT / 'vendor'
GLOBE = HERE / 'globe'

DESIGNS = {'atlas': 'Atlas', 'orbital': 'Orbital', 'grid': 'Grid'}


def read(path):
    return path.read_text(encoding='utf-8')


def change(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Expected a single template anchor: {old}')
    return text.replace(old, new)


def font(name, path, weight=500, style='normal'):
    data = b64encode(path.read_bytes()).decode('ascii')
    return f"@font-face{{font-family:'{name}';src:url(data:font/woff2;base64,{data}) format('woff2');font-style:{style};font-weight:{weight};font-display:swap}}"


def css():
    f = HERE / 'fonts'
    return '\n'.join((font('Newsreader', f / 'newsreader.woff2'),
        font('Newsreader', f / 'newsreader-italic.woff2', style='italic'),
        font('Space Grotesk', f / 'space.woff2'), font('Barlow Condensed', f / 'barlow.woff2', 600),
        font('IBM Plex Mono', f / 'plex.woff2', 400), font('DM Mono', VENDOR / 'dm-mono.woff2', 400),
        read(SRC / 'style.css'), read(HERE / 'variants.css'), read(HERE / 'year.css')))


def app():
    js = read(SRC / 'app.js')
    # Keep the flat public site independent. The new dashboard shares its data logic.
    result = change(change(change(change(change(change(js,
        "hour: '2-digit', minute: '2-digit', hourCycle: 'h23'", "hour: '2-digit', minute: '2-digit', hourCycle: 'h12'"),
        "const time = (instant, zone) => formatter(zone, timeOptions).format(instant);",
        "const time = (instant, zone) => clockText(parts(instant, zone, timeOptions));\n    const clockText = ({hour, minute, dayPeriod}) => `${hour}:${minute} ${dayPeriod.toUpperCase()}`;\n    function paintTime(node, value) {\n      const [clock, period] = value.split(' ');\n      if (node.dataset.value === value) return;\n      node.dataset.value = value;\n      node.replaceChildren(document.createTextNode(clock), ...(period ? [document.createTextNode(' '), html('span', 'meridiem', period)] : []));\n    }"),
        "$('map-pins').replaceChildren(...pins);", "$('map-pins').replaceChildren(...pins);\n      window.AlmanacGlobe?.setPlace(place, cities);"),
        "write($('local-time'), `${local.hour}:${local.minute}`);", "paintTime($('local-time'), clockText(local));"),
        "write(clockTime, `${cityTime.hour}:${cityTime.minute}`);", "paintTime(clockTime, clockText(cityTime));"),
        "locate.addEventListener('click', () => {", "locate.addEventListener('click', async () => {\n      if (globalThis.chrome?.runtime?.id && chrome.permissions) {\n        try {\n          const granted = await chrome.permissions.request({ permissions: ['geolocation'] });\n          if (!dialog.open) return;\n          if (!granted) { write(status, 'Location permission denied. Search for a city.'); return; }\n        } catch { write(status, 'Location unavailable. Search for a city.'); return; }\n      }" )
    for event in ('sunrise', 'sunset'):
        instant = 'rise' if event == 'sunrise' else 'set'
        result = change(result, f"write($('{event}'), label(sun?.{instant}));", f"paintTime($('{event}'), label(sun?.{instant}));")
    return local_weather(result)


def number_effects(js):
    clock_content = "      node.replaceChildren(document.createTextNode(clock), ...(period ? [document.createTextNode(' '), html('span', 'meridiem', period)] : []));"
    js = change(js, clock_content, clock_content + '\n      if (period) scanNumber(node);')
    js = change(js, '    async function refreshWeather(force = false) {', '''    function scanNumber(node) {
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

    async function refreshWeather(force = false) {''')
    js = change(js, '      const target = displayedPlace();', '''      const target = displayedPlace();
      if ($('weather-temp').textContent === '—') {
        paintTemperature('—', true);
        write($('weather-condition'), 'Loading weather…');
      }''')
    js = change(js, "      write($('weather-temp'), '—');\n      weatherIcon.replaceChildren();",
        "      paintTemperature('—');\n      weatherIcon.replaceChildren();")
    js = change(js, "        write($('weather-temp'), '—');", "        paintTemperature('—');")
    return change(js, "        write($('weather-temp'), String(Math.round(current.temperature_2m)));",
        "        paintTemperature(String(Math.round(current.temperature_2m)));")


GLOBE_MARKUP = '''<div id="globe-stage"><canvas id="globe" aria-label="Interactive Earth with time zones, day and night, and ISS position. Use arrow keys to rotate." tabindex="0"></canvas></div><div class="globe-controls"><div><button id="globe-home" type="button" aria-label="Center selected city" title="Center selected city"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><circle cx="12" cy="12" r="7"/><circle cx="12" cy="12" r="2"/><path d="M12 1v4m0 14v4M1 12h4m14 0h4"/></svg></button><button id="globe-iss" type="button" aria-label="Center the International Space Station" title="Center the International Space Station">ISS</button></div><span id="iss-status"></span></div><svg hidden aria-hidden="true"><g id="map-pins"></g></svg>'''
YEAR_MARKUP = '''<section class="year" id="year-progress" aria-labelledby="year-title"><div class="section-line"><h2 class="eyebrow" id="year-title">Year progress</h2><span class="year-number"></span></div><div class="year-content"><div class="year-readout"><span class="year-percent"></span><span class="year-count"></span></div><div class="year-days" aria-hidden="true"></div></div></section>'''
SETTINGS_BUTTON = '''<button type="button" class="icon-button" id="settings-open" aria-label="Appearance and data sources" title="Appearance and data sources" aria-haspopup="dialog"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" aria-hidden="true"><path d="M5 6h14M5 12h14M5 18h14"/><path d="M9 4v4m6 2v4m-4 2v4" stroke-width="2"/></svg></button>'''
SETTINGS = '''<dialog id="settings" aria-labelledby="settings-label"><div class="settings-title"><h2 id="settings-label">Settings</h2><button class="icon-button" type="button" id="settings-close" aria-label="Close settings">×</button></div><label for="appearance">Appearance</label><select id="appearance"><option value="atlas">Atlas</option><option value="orbital">Orbital</option><option value="grid">Grid</option></select><details><summary>Data sources</summary><p>Weather by <a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a> (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>). Temperatures are rounded. City search uses <a href="https://www.geonames.org/" target="_blank" rel="noopener noreferrer">GeoNames</a> via Open-Meteo.</p><p>ISS positions by <a href="https://wheretheiss.at/" target="_blank" rel="noopener noreferrer">Where the ISS at?</a>. Boundaries by Natural Earth.</p></details></dialog>'''
CITY_CLOCK_SETTINGS = '''<section class="city-clock-settings" aria-labelledby="city-clocks-title">
  <h3 id="city-clocks-title">City clocks</h3>
  <p id="city-clocks-empty" hidden>No city clocks.</p>
  <ul id="city-clock-list"></ul>
  <button type="button" id="add-city-clock" aria-haspopup="dialog">Add city</button>
</section>'''
WEB_STYLE = '''.masthead-link{display:inline-flex;align-items:center;gap:.35em;min-height:44px;color:var(--quiet);text-decoration:none;text-underline-offset:4px;white-space:nowrap}.masthead-link:hover,.masthead-link:focus-visible{color:var(--ink);text-decoration:underline}.masthead-link[data-primary]{color:var(--ink)}.masthead-link svg{width:1.3em;height:1.3em;flex:none}
[data-desktop-safari] .masthead-link[data-primary]{display:none}'''
DESKTOP_SAFARI = r'''<script>
  // Safari on iPad can report a Mac user agent in desktop mode.
  if (navigator.maxTouchPoints <= 1 && /\(Macintosh;/.test(navigator.userAgent) &&
      /\bVersion\/[\d.]+ Safari\/[\d.]+$/.test(navigator.userAgent)) {
    document.documentElement.setAttribute('data-desktop-safari', '');
  }
</script>'''
STORE_URL = 'https://chromewebstore.google.com/detail/home-new-tab/pgeahicgbpcfobknhbgjhlldjpapbgol'
GITHUB_ICON = '<svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>'
FIRST_PAINT = '''<style>
:root{color-scheme:light dark;--theme-paper:light-dark(#fafafa,#141414);--theme-ink:light-dark(#131313,#f3f3f3);background:var(--theme-paper)}
:root[data-theme=light]{color-scheme:light}
:root[data-theme=dark]{color-scheme:dark}
</style>'''


def page(design, styles, scripts, fixed=False):
    source = read(SRC / 'page.html')
    fixed_attr = ' data-fixed-design="true"' if fixed else ''
    source = change(source, '<html lang="en">', f'<html lang="en" data-design="{design}"{fixed_attr}>')
    source = change(source, '<style>/* @FONTS@ */\n/* @CSS@ */</style>', styles)
    globe = GLOBE_MARKUP.replace('id="globe-home"', 'id="globe-home" data-managed="true"').replace('Center selected city', 'Return to my location')
    source = change(source, '<!-- @MAP@ -->', globe)
    source = change(source, '<span id="place-name">Madrid</span>', '<span id="place-name">Set location</span>')
    source = change(source, '      <div class="sky">', '      <div class="sky">\n' + YEAR_MARKUP + '\n        <div class="local-panels">')
    source = change(source, '        <section class="moon"', '        </div>\n        <section class="moon"')
    # Put the phase after the illustration in reading order as well as visually.
    match = re.search(r'            (<div><div id="moon-phase"[^\n]*</div>)\n(            <svg class="lunar-art"[\s\S]*?            </svg>)', source)
    source = change(source, match[0], match[2] + '\n            ' + match[1])
    source = change(source, 'r="49" fill="#d8d8d8" stroke="#929292"', 'r="49" fill="#343434" stroke="#777"')
    source = source.replace('slope="2" intercept="-.62"', 'slope="1.58" intercept="-.31"')
    source = change(source, 'fill="#acacac"', 'fill="#bdbdbd"')
    source = change(source, '<g clip-path="url(#moon-disk)">', '<g clip-path="url(#moon-disk)"><rect x="15" y="15" width="98" height="98" filter="url(#lunar-grain)" opacity=".15"/>')
    source = change(source, 'stroke-width=".85"><circle r="8.6"', 'stroke-width=".85"><circle class="sun-halo" r="10.2" stroke-dasharray="1 2"/><circle r="8.6"')
    source = change(source, 'stroke-width=".7"><circle r="7"', 'stroke-width=".7"><circle class="sun-halo" r="9.6" fill="none" stroke-dasharray="1 2"/><circle r="7"')
    settings_button = SETTINGS_BUTTON.replace('Appearance and data sources', 'Data sources') if fixed else SETTINGS_BUTTON
    source = change(source, '<span class="eyebrow zone" id="local-zone"></span>', f'<div></div><div class="masthead-right"><span class="eyebrow zone" id="local-zone"></span>{settings_button}</div>')
    source = change(source, '<footer class="credits"><a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer">Open-Meteo</a></footer>', '')
    settings = SETTINGS if not fixed else re.sub(r'<label for="appearance">.*?</select>', '', SETTINGS)
    source = change(source, '<script>/* @ASTRONOMY@ */</script>\n<script>/* @APP@ */</script>', settings + '\n' + scripts)
    return source


def type_proposal(style, assets, footer):
    icons = {
        'Sunrise': '<path d="M2 17h20M5 15a7 7 0 0 1 14 0M12 2v8m-3-5 3-3 3 3"/>',
        'Sunset': '<path d="M2 17h20M5 15a7 7 0 0 1 14 0M12 1v8m-3-3 3 3 3-3"/>',
    }
    plain_app = change(assets['dashboard.js'], "const button = html('button', 'clock');\n      button.type = 'button';", "const button = html('div', 'clock');")
    plain_app = change(plain_app, "      button.addEventListener('click', () => {\n        explored = city;\n        renderGlobe(true);\n      });\n", '')
    plain_app = change(plain_app, "        button.setAttribute('aria-pressed', String(city === selectedCity));\n", '')
    type_assets = [assets['appearance.js'], assets['astronomy.js'], plain_app, assets['year.js']]
    scripts = '\n'.join(f'<script>\n{value}\n</script>' for value in type_assets)
    source = page('grid', f'<style>{style}\n{read(HERE / "type.css")}</style>', scripts, fixed=True)
    source = change(source, 'data-fixed-design="true"', 'data-fixed-design="true" data-presentation="type"')
    source = re.sub(r'        <div class="map-frame">[\s\S]*?        </div>\n', '', source, count=1)
    source = re.sub(r'          <svg class="solar-art"[\s\S]*?</svg>\n', '', source, count=1)
    # Keep an inert marker for the shared sunrise/sunset renderer.
    source = change(source, '<div class="sun-times">', '<span id="sun-marker" hidden></span><div class="sun-times">')
    for name, path in icons.items():
        label = f'<span class="eyebrow">{name}</span>'
        icon = f'<svg class="sun-pictogram" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.15" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{path}</svg>'
        source = change(source, label, icon + label)
    source = change(source, '<div class="year-days" aria-hidden="true"></div>', '<div class="year-days" hidden></div>')
    source = change(source, '<circle cx="64" cy="64" r="55" fill="none" stroke="#aeaeae" stroke-width=".65" stroke-dasharray="1 3"/>', '')
    source = change(source, '<path d="M64 4v6m0 108v6M4 64h6m108 0h6" stroke="#7d7d7d" stroke-width=".7"/>', '')
    return source + footer


def globe_page(styles, scripts, appearance):
    source = page('grid', styles, scripts, fixed=True)
    source = change(source, 'data-fixed-design="true"', 'data-fixed-design="true" data-presentation="center"')
    source = change(source, '<meta name="color-scheme" content="light">',
        '<meta name="color-scheme" content="light dark">\n' + appearance + '\n' + FIRST_PAINT)
    source = change(source, YEAR_MARKUP, '')
    source = change(source, '<span class="degrees" aria-label="degrees Celsius">',
        '<span id="weather-loading" hidden aria-hidden="true"><span></span><span></span><span></span></span>'
        '<span class="degrees" id="weather-unit" aria-label="degrees Celsius">')
    source = change(source, '<span id="weather-condition">', '<span id="weather-condition" role="status">')

    source = re.sub(r'            <g class="sun-noon"[^\n]*</g>\n', '', source, count=1)
    marker_close = 'm17 17 2.8 2.8"/></g>'
    moon_glyph = '''<g class="sun-night-glyph" transform="scale(.22) translate(-64 -64)" stroke="none">
      <circle cx="64" cy="64" r="49" fill="#ddd"/>
      <use href="#moon-lit" fill="#171717"/>
      <circle cx="64" cy="64" r="49" fill="none" stroke="#171717" stroke-width="4.5"/>
    </g>'''
    source = change(source, marker_close, marker_close[:-4] + moon_glyph + '</g>')
    sun_times = re.search(r'          <div class="sun-times">[^\n]+', source)[0]
    source = change(source, sun_times, sun_times + '\n          <p id="night-progress"></p>')
    clocks = '        <div id="clocks" class="clock-grid" aria-label="City clocks"></div>'
    source = change(source, clocks, '')
    source = change(source, '  </main>', clocks + '\n  </main>')
    source = change(source, '        <div class="section-line"><h2 class="eyebrow" id="atlas-title">World time</h2><span class="figure-index" aria-hidden="true">01</span></div>', '        <h2 id="atlas-title" class="sr-only">World time</h2>')
    # The Moon is drawn as a map on a canvas, like the globe (see moon_sky.py).
    moon = '<canvas class="lunar-art" id="moon-canvas" width="158" height="158" aria-hidden="true"></canvas>'
    source, count = re.subn(r'<svg class="lunar-art"[\s\S]*?</svg>', lambda _: moon, source)
    if count != 1:
        raise ValueError('Expected one Moon illustration')
    # The sun cursor's night glyph still draws the current phase from this path.
    solar = '<svg class="solar-art" viewBox="0 0 320 100" aria-hidden="true" fill="none">'
    source = change(source, solar, solar + '<defs><path id="moon-lit" d="M0 0"/></defs>')
    source = change(source, 'Boundaries by Natural Earth.</p>', 'Boundaries by Natural Earth.</p><p>Lunar maria traced from the Moon mosaic by <a href="https://svs.gsfc.nasa.gov/5001/" target="_blank" rel="noopener noreferrer">NASA’s Scientific Visualization Studio</a>. Nearby place labels use a reduced <a href="https://www.geonames.org/" target="_blank" rel="noopener noreferrer">GeoNames</a> gazetteer (<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank" rel="noopener noreferrer">CC BY 4.0</a>).</p>')
    source = change(source, 'aria-label="Data sources" title="Data sources"', 'aria-label="Settings" title="Settings"')
    source = change(source, '<details><summary>Data sources</summary>', '<label for="theme">Theme</label><select id="theme"><option value="system">System</option><option value="light">Light</option><option value="dark">Dark</option><optgroup label="Color themes"><option value="gruvbox">Gruvbox</option><option value="deep-ocean">Deep Ocean</option><option value="tokyo-night">Tokyo Night</option><option value="dracula">Dracula</option><option value="oxblood">Oxblood</option><option value="unit-01">Unit‑01</option></optgroup></select><details><summary>Data sources</summary>')
    source = change(source, '<details><summary>Data sources</summary>', CITY_CLOCK_SETTINGS + '<details><summary>Data sources</summary>')
    return source


def clock_page(styles, scripts, layout, *, appearance):
    if layout not in ('shoulders', 'meridian', 'inline'):
        raise ValueError(f'Unknown date and time layout: {layout}')
    source = globe_page(styles, scripts, appearance)
    locate = '<button type="button" class="locate" id="locate">Use my location</button>'
    disclosure = ('<p class="geo-disclosure" id="geo-disclosure">Your browser saves your last approximate location. '
                  'Open-Meteo receives approximate coordinates for weather. Choose a city to remove the saved device location.</p>')
    source = change(source, locate, disclosure + '\n  ' + locate.replace('id="locate"', 'id="locate" aria-describedby="geo-disclosure"'))
    source = change(source, 'data-presentation="center"', f'data-presentation="center" data-clock-layout="{layout}"')
    zone = '<span class="eyebrow zone" id="local-zone"></span>'
    clock = '<div id="local-time" class="local-time"></div>'
    source = change(source, zone, '')
    readout = '<div class="current-clock" aria-label="Local time">' + clock + zone + '</div>'
    return change(source, clock, readout)


def web_clock_page(styles, scripts, layout, *, appearance):
    source = clock_page(styles, scripts, layout, appearance=appearance + '\n' + DESKTOP_SAFARI)
    links = (
        f'<a class="eyebrow masthead-link" data-primary href="{STORE_URL}" target="_blank" rel="noopener noreferrer">'
        'Install extension <span aria-hidden="true">↗</span></a>'
        '<a class="eyebrow masthead-link" href="https://github.com/cris7ian/pale-blue-dot-tab" title="Pale Blue Dot Tab on GitHub" target="_blank" rel="noopener noreferrer">'
        f'{GITHUB_ICON}GitHub</a>'
    )
    if layout == 'meridian':
        source = change(source, '<html lang="en"', '<html lang="en" data-web="true"')
        footer = f'<footer class="mobile-links">{links}</footer>'
        source = change(source, '  </main>', f'  </main>\n  {footer}')
    return change(source, '<div></div><div class="masthead-right">',
        f'<div class="masthead-left">{links}</div><div class="masthead-right">')


def main():
    EXT.mkdir(exist_ok=True)
    PREVIEW.mkdir(exist_ok=True)
    assets = {'appearance.js': read(HERE / 'appearance.js'), 'astronomy.js': read(VENDOR / 'astronomy.browser.min.js')}
    for name in json.loads(read(GLOBE / 'scripts.json')):
        name_path = Path(name)
        if name_path.is_absolute() or '..' in name_path.parts or name_path.name in assets:
            raise ValueError(f'Invalid or duplicate globe asset: {name}')
        assets[name_path.name] = read(GLOBE / name_path)
    standalone_app = app()
    city_data = b64encode((HERE / 'cities5000.json.gz').read_bytes()).decode('ascii')
    assets['nearby.js'] = change(read(HERE / 'nearby.js'), '/* @CITY_GZIP@ */', city_data)
    assets['dashboard.js'] = number_effects(city_clocks(moon_sky(solar_cursor(exploring_weather(standalone_app))), change))
    for previous in ('solar.js', 'year.js'):
        (EXT / previous).unlink(missing_ok=True)
    style = css()
    licenses = [*sorted((HERE / 'fonts').glob('*-OFL.txt')), VENDOR / 'dm-mono-OFL.txt', *sorted(GLOBE.glob('*.LICENSE'))]
    notices = 'Natural Earth v5.1.2 map data: public domain.\n\n' + '\n\n'.join(f'{p.name}\n{read(p)}' for p in licenses)
    (EXT / 'NOTICES.txt').write_text(notices, encoding='utf-8')
    for name, value in assets.items():
        if re.search(r'</script', value, re.I):
            raise ValueError(f'Script terminator in {name}')
        (EXT / name).write_text(value, encoding='utf-8')
    centered_style = '\n'.join((style, read(HERE / 'center.css'), read(HERE / 'clock-layouts.css'), read(HERE / 'theme.css')))
    (EXT / 'home.css').write_text(centered_style, encoding='utf-8')
    (EXT / 'manifest.json').write_text(read(HERE / 'manifest.json'), encoding='utf-8')
    dashboard_assets = {name: value for name, value in assets.items() if name != 'appearance.js'}
    deferred = '\n'.join(f'<script defer src="{name}"></script>' for name in dashboard_assets)
    (EXT / 'newtab.html').write_text(clock_page('<link rel="stylesheet" href="home.css">', deferred, 'meridian',
        appearance='<script blocking="render" src="appearance.js"></script>'), encoding='utf-8')
    inline = '\n'.join(f'<script>\n{value}\n</script>' for value in dashboard_assets.values())
    appearance = f'<script>\n{assets["appearance.js"]}\n</script>'
    footer = '\n<!--\n' + notices.replace('--', '—') + '\n-->\n'
    web_style = f'<style>{centered_style}\n{WEB_STYLE}\n{read(HERE / "mobile.css")}</style>'
    for layout in ('shoulders', 'meridian', 'inline'):
        (PREVIEW / f'globe-{layout}.html').write_text(web_clock_page(web_style, inline, layout, appearance=appearance) + footer, encoding='utf-8')
    (PREVIEW / 'globe.html').write_text(web_clock_page(web_style, inline, 'meridian', appearance=appearance) + footer, encoding='utf-8')
    del assets['nearby.js']
    assets['dashboard.js'] = standalone_app
    assets['year.js'] = read(HERE / 'year.js')
    inline = '\n'.join(f'<script>\n{value}\n</script>' for value in assets.values())
    (PREVIEW / 'grid-release.html').write_text(page('grid', f'<style>{style}</style>', inline, fixed=True) + footer, encoding='utf-8')
    for design in DESIGNS:
        (PREVIEW / f'{design}.html').write_text(page(design, f'<style>{style}</style>', inline) + footer, encoding='utf-8')
    (PREVIEW / 'type.html').write_text(type_proposal(style, assets, footer), encoding='utf-8')

    links = ''.join(f'<li><a href="{name}.html?design={name}">{html.escape(label)}</a></li>' for name, label in DESIGNS.items())
    links += '<li><a href="type.html">Type &amp; Icons</a></li>'
    links += '<li><a href="globe.html">Globe</a></li>'
    links += ''.join(f'<li><a href="globe-{name}.html">Globe · {name.title()}</a></li>' for name in ('shoulders', 'meridian', 'inline'))
    (PREVIEW / 'index.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Pale Blue Dot Tab — Proposals</title><style>body{{margin:9vh auto;width:min(80%,600px);font:24px/1.8 Georgia;background:#fafafa;color:#111}}a{{color:inherit}}li{{border-top:1px solid #ccc;padding:8px}}ul{{padding:0;list-style:none}}</style><h1>Home</h1><ul>{links}</ul></html>', encoding='utf-8')
    print('Built local proposals and the globe release (live site unchanged)')


if __name__ == '__main__':
    main()
