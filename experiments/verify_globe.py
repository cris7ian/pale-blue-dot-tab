"""Run `uv run --with playwright python experiments/verify_globe.py` after build."""
import argparse
from datetime import datetime
from pathlib import Path
import re
from tempfile import TemporaryDirectory
from urllib.parse import parse_qs, urlsplit

from playwright.sync_api import Error, expect, sync_playwright

HERE = Path(__file__).resolve().parent
ARTIFACTS = HERE / 'artifacts'
CLK = re.compile(r'^\d{1,2}:\d{2} (AM|PM)$')
NUMBER = re.compile(r'^-?\d+$')
DESIGNS = {'atlas': 'Newsreader', 'orbital': 'Space Grotesk', 'grid': 'Barlow Condensed'}
BASE = 'http://127.0.0.1:4174/'

HOME = f'{BASE}globe.html'
PROVIDERS = re.compile(r'^https://(?:(?:api|geocoding-api)\.open-meteo\.com|api\.wheretheiss\.at)/')
# The Moon canvas shows its traced maria: some opaque pixels, in more than one tone.
MOON_PAINTED = '''() => {
  const canvas = document.getElementById('moon-canvas');
  if (!window.AlmanacMoonData || !canvas.width) return false;
  const data = canvas.getContext('2d').getImageData(0, 0, canvas.width, canvas.height).data;
  const tones = new Set();
  for (let i = 0; i < data.length; i += 4) if (data[i + 3] === 255) tones.add(data[i]);
  return tones.size > 4;
}'''
CITIES = {
    'Madrid': ('Spain', 40.42, -3.70, 'Europe/Madrid'),
    'Kathmandu': ('Nepal', 27.7172, 85.324, 'Asia/Kathmandu'),
    'Caracas': ('Venezuela', 10.488, -66.879, 'America/Caracas'),
    'Longyearbyen': ('Svalbard and Jan Mayen', 78.22, 15.65, 'Arctic/Longyearbyen'),
}


def mock_providers(context):
    context.route(re.compile(r'^https?://(?!127\.0\.0\.1:4174/)'), lambda route: route.abort())

    def respond(route):
        url = urlsplit(route.request.url)
        query = parse_qs(url.query)
        if url.path == '/v1/search':
            names = query['name']
            if names == ['Kathmandu']:
                names = ['Kathmandu', 'Caracas']  # Offer a duplicate clock option.
            results = []
            for name in names:
                if name in CITIES:
                    country, lat, lon, zone = CITIES[name]
                    results.append(dict(name=name, country=country, latitude=lat, longitude=lon, timezone=zone))
            payload = {'results': results}
        elif url.path == '/v1/forecast':
            zone = {'27.72': 'Asia/Kathmandu', '35.68': 'Asia/Tokyo'}.get(query['latitude'][0], 'Europe/Madrid')
            payload = {'timezone': zone, 'current': {'temperature_2m': 19, 'weather_code': 0, 'is_day': 1}}
        elif url.path == '/v1/satellites/25544/positions':
            payload = [dict(id=25544, units='kilometers', timestamp=int(stamp),
                            latitude=12, longitude=20 + i, altitude=420)
                       for i, stamp in enumerate(query['timestamps'][0].split(','))]
        else:
            route.abort()
            return
        route.fulfill(json=payload, headers={'Access-Control-Allow-Origin': '*'})

    context.route(PROVIDERS, respond)


def preview_page(browser, **options):
    page = browser.new_page(**options)
    mock_providers(page.context)
    return page


def screenshot(page, name, enabled):
    if enabled:
        ARTIFACTS.mkdir(exist_ok=True)
        page.screenshot(path=ARTIFACTS / f'{name}.png', full_page=True)


def manual_weather(page):
    page.locator('#weather-place').click()
    page.locator('#city-query').fill('Madrid')
    page.locator('#city-search button[type=submit]').click()
    page.locator('#city-results button').filter(has_text=re.compile('Madrid.*Spain')).first.click(timeout=17000)
    expect(page.locator('#place-name')).to_contain_text('Madrid')
    expect(page.locator('#weather-temp')).to_have_text(NUMBER, timeout=17000)


def collect_errors(page, errors):
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda message: errors.append(message.text) if message.type == 'error' and 'Content Security Policy' in message.text else None)


def wait_frame(page):
    page.evaluate('document.fonts.ready')
    page.evaluate('new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))')


def check(page, design):
    expect(page).to_have_title('Pale Blue Dot Tab')
    expect(page.locator('html')).to_have_attribute('data-design', design)
    expect(page.locator('#local-time')).to_have_text(CLK)
    expect(page.locator('#sunrise')).to_have_text(CLK)
    expect(page.locator('#sunset')).to_have_text(CLK)
    expect(page.locator('#clocks button')).to_have_count(8)
    for clock in page.locator('.clock-time').all():
        expect(clock).to_have_text(CLK)
    expect(page.locator('#weather-temp')).to_have_text(NUMBER, timeout=17000)
    expect(page.get_by_role('link', name='Open-Meteo', exact=True)).not_to_be_visible()
    wait_frame(page)
    assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
    assert page.evaluate("document.fonts.check('" + ('600' if design == 'grid' else '500') + " 32px \"" + DESIGNS[design] + "\"')")
    assert page.locator('#globe').evaluate('(el) => el.width > 150 && el.height > 150')
    assert re.search(r'\d', page.locator('#moon-percent').inner_text())
    expect(page.locator('#solar-system')).to_have_count(0)
    if page.locator('html').get_attribute('data-presentation') == 'center':
        expect(page.locator('#year-progress, table')).to_have_count(0)
        assert page.locator('#clocks').bounding_box()['y'] >= page.locator('#globe').bounding_box()['y'] + page.locator('#globe').bounding_box()['height']
        return
    expect(page.locator('#year-progress')).to_be_visible()
    expect(page.locator('.year-month')).to_have_count(12)
    expect(page.locator('.year-square[data-state=today]')).to_have_count(1)
    assert page.locator('.year-square').count() in (365, 366)
    atlas = page.locator('.atlas').bounding_box()
    year = page.locator('#year-progress').bounding_box()
    moon = page.locator('.lunar-art').bounding_box()
    phase = page.locator('#moon-phase').bounding_box()
    assert phase['y'] >= moon['y'] + moon['height']
    icon = page.locator('#weather-icon').bounding_box()
    width = page.evaluate('innerWidth')
    if width > 900:
        assert abs(atlas['y'] - year['y']) < 2 and year['x'] >= atlas['x'] + atlas['width'] - 2
        assert moon['width'] >= 155 and icon['width'] >= 72
    else:
        assert year['y'] >= atlas['y'] + atlas['height'] - 2 and moon['width'] >= 155 and icon['width'] >= 43


def status(page):
    expect(page.locator('#globe-iss')).to_have_attribute('aria-disabled', 'false', timeout=17000)
    expect(page.locator('#iss-status')).to_be_empty()


def globe_focus(page):
    globe = page.locator('#globe')
    globe.click()
    expect(globe).to_be_focused()
    expect(globe).to_have_css('outline-style', 'none')
    page.keyboard.press('ArrowRight')
    expect(globe).to_have_css('outline-style', 'solid')
    globe.click()
    expect(globe).to_have_css('outline-style', 'none')
    page.keyboard.press('Tab')
    expect(page.locator('#globe-home')).to_be_focused()
    page.keyboard.press('Shift+Tab')
    expect(globe).to_be_focused()
    expect(globe).to_have_css('outline-style', 'solid')


def leap_year(browser):
    page = preview_page(browser, viewport={'width': 320, 'height': 640}, timezone_id='America/New_York')
    page.clock.install(time=datetime.fromisoformat('2028-02-29T23:59:45-05:00'))
    page.goto(f'{BASE}grid-release.html')
    expect(page.locator('.year-square')).to_have_count(366)
    expect(page.locator('.year-count')).to_have_text('060 / 366')
    expect(page.locator('.year-square[data-state=today]')).to_have_attribute('title', '29 February 2028')
    page.clock.fast_forward(35_000)
    expect(page.locator('.year-count')).to_have_text('061 / 366')
    expect(page.locator('.year-square[data-state=today]')).to_have_attribute('title', '1 March 2028')
    assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
    page.close()


def type_proposal(browser, errors, screenshots):
    for width, height in ((1440, 900), (390, 844), (320, 720)):
        page = preview_page(browser, viewport={'width': width, 'height': height}, timezone_id='Europe/Madrid')
        collect_errors(page, errors)
        assert page.goto(f'{BASE}type.html').ok
        manual_weather(page)
        expect(page.locator('#clocks .clock')).to_have_count(8)
        expect(page.locator('#clocks button')).to_have_count(0)
        expect(page.locator('#globe')).to_have_count(0)
        expect(page.locator('.sun-pictogram')).to_have_count(2)
        expect(page.locator('#sunset')).to_have_text(CLK)
        expect(page.locator('.year-percent')).to_have_text(re.compile(r'^\d+%$'))
        expect(page.locator('.year-days')).to_be_hidden()
        wait_frame(page)
        problems = page.evaluate('''() => [...document.querySelectorAll('.masthead, main *')]
          .filter(el => el instanceof HTMLElement && el.getClientRects().length)
          .filter(el => ['Top','Right','Bottom','Left'].some(side => parseFloat(getComputedStyle(el)[`border${side}Width`]) > 0))
          .map(el => el.className)''')
        assert not problems, problems
        assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
        if width != 320:
            screenshot(page, f'type-{width}', screenshots)
        page.close()


def website_layout(browser, errors, screenshots):
    for width, height in ((1440, 900), (390, 844), (320, 720)):
        mobile = width <= 650
        page = preview_page(browser, viewport={'width': width, 'height': height}, timezone_id='Europe/Madrid',
                            has_touch=mobile, is_mobile=mobile)
        collect_errors(page, errors)
        assert page.goto(HOME).ok
        manual_weather(page)
        check(page, 'grid')
        status(page)
        globe = page.locator('#globe').bounding_box()
        cities = page.locator('#clocks').bounding_box()
        weather = page.locator('.weather').bounding_box()
        sun = page.locator('.sun').bounding_box()
        moon = page.locator('.moon').bounding_box()
        phase = page.locator('#moon-phase')
        assert phase.evaluate('el => getComputedStyle(el).whiteSpace === "nowrap" && el.scrollWidth <= el.clientWidth && parseFloat(getComputedStyle(el).fontSize) <= 23')
        assert sun['y'] >= weather['y'] + weather['height'] - 1
        assert cities['y'] >= globe['y'] + globe['height']
        if not mobile:
            date = page.locator('.date-block').bounding_box()
            clock = page.locator('.date-line .current-clock').bounding_box()
            assert date['x'] + date['width'] <= clock['x']
            assert max(date['y'] + date['height'], clock['y'] + clock['height']) <= globe['y']
            assert weather['x'] < globe['x'] < moon['x']
            assert abs(globe['x'] + globe['width'] / 2 - width / 2) < 15
            assert cities['y'] + cities['height'] <= height - 34
        else:
            clock = page.locator('.current-clock').bounding_box()
            controls = page.locator('.globe-controls').bounding_box()
            assert clock['y'] + clock['height'] < globe['y']
            assert controls['y'] + controls['height'] <= weather['y']
            assert weather['y'] + weather['height'] <= min(sun['y'], moon['y'])
            assert cities['y'] >= max(sun['y'] + sun['height'], moon['y'] + moon['height'])
            assert weather['y'] + weather['height'] < height
            expect(page.locator('#globe')).to_have_css('touch-action', 'pan-y pinch-zoom')
            for selector in ('#settings-open', '#weather-place', '#globe-home', '#globe-iss'):
                target = page.locator(selector).bounding_box()
                assert target['height'] >= 44
        website_links(page)
        assert page.evaluate(MOON_PAINTED), 'The Moon map is drawn'
        screenshot(page, f'globe-{width}', screenshots)
        if width != 320:
            city_rotation(page)
        else:
            palette_options(page)
        page.close()


def city_rotation(page):
    tokyo = page.locator('#clocks').get_by_role('button', name=re.compile('Tokyo'))
    before = page.locator('#globe').evaluate('(el) => el.toDataURL()')
    local = page.locator('#place-name').inner_text()
    explore_weather = page.locator('html').get_attribute('data-presentation') == 'center'
    home_sunrise = page.locator('#sunrise').inner_text()
    if explore_weather:
        with page.expect_request(lambda req: 'latitude=35.68' in req.url and 'longitude=139.69' in req.url):
            tokyo.click()
        expect(page.locator('#weather-temp')).to_have_text(NUMBER, timeout=17000)
        expect(page.locator('#place-name')).to_have_text('Tokyo')
        assert page.locator('#sunrise').inner_text() != home_sunrise
    else:
        tokyo.click()
        expect(page.locator('#place-name')).to_have_text(local)
    expect(tokyo).to_have_attribute('aria-pressed', 'true')
    page.wait_for_function('(before) => document.querySelector("#globe").toDataURL() !== before', arg=before, timeout=4000)
    page.locator('#globe-home').click()
    expect(tokyo).to_have_attribute('aria-pressed', 'false')
    expect(page.locator('#place-name')).to_have_text(local)
    expect(page.locator('#sunrise')).to_have_text(home_sunrise)


def configurable_clocks(page, peer=None):
    page.clock.set_fixed_time(datetime.fromisoformat('2026-11-26T12:00:00+00:00'))
    clocks = page.locator('#clocks')
    expect(clocks.locator('.clock-city')).to_have_text([
        'Los Angeles', 'New York', 'Caracas', 'London', 'Madrid', 'Dubai', 'Tokyo', 'Sydney',
    ])
    expect(clocks.get_by_role('button', name=re.compile('Caracas')).locator('.clock-time')).to_have_text(
        re.compile(r'^0?8:00 AM$'))
    home = page.locator('#place-name').inner_text()
    page.locator('#settings-open').click()
    page.get_by_role('button', name='Add city', exact=True).click()
    expect(page.get_by_role('button', name='Use my location')).to_be_hidden()
    page.locator('#city-query').fill('Kathmandu')
    page.locator('#city-search button[type=submit]').click()
    page.get_by_role('button', name='Add Caracas, Venezuela').click()
    expect(page.locator('#location-status')).to_contain_text('already in your city clocks')
    page.get_by_role('button', name='Add Kathmandu, Nepal').click()
    expect(page.locator('#add-city-clock')).to_be_focused()
    expect(page.locator('#settings')).to_be_visible()
    expect(clocks.locator('.clock-city')).to_have_text([
        'Los Angeles', 'New York', 'Caracas', 'London', 'Madrid', 'Dubai', 'Kathmandu', 'Tokyo', 'Sydney',
    ])
    expect(page.locator('#city-clock-list li span').nth(6)).to_have_text('Kathmandu, Nepal')
    if peer:
        expect(peer.locator('#clocks .clock-city').nth(6)).to_have_text('Kathmandu')
    page.get_by_role('button', name='Close settings').click()
    expect(page.locator('#place-name')).to_have_text(home)
    assert page.evaluate('document.documentElement.scrollWidth === innerWidth')
    page.reload()
    kathmandu = clocks.get_by_role('button', name=re.compile('Kathmandu'))
    expect(kathmandu.locator('.clock-time')).to_have_text(re.compile(r'^0?5:45 PM$'))
    with page.expect_request(lambda req: 'latitude=27.72' in req.url and 'longitude=85.32' in req.url):
        kathmandu.click()
    expect(page.locator('#place-name')).to_have_text('Kathmandu')
    expect(page.locator('#weather-place')).to_have_attribute('aria-label', 'Change weather location: Kathmandu, Nepal')
    expect(page.locator('#weather-temp')).to_have_text('19')
    page.locator('#settings-open').click()
    page.get_by_role('button', name='Remove Kathmandu, Nepal').click()
    expect(page.locator('#place-name')).to_have_text(home)
    remove_buttons = page.locator('#city-clock-list button')
    for remaining in range(7, -1, -1):
        remove_buttons.first.click()
        expect(remove_buttons).to_have_count(remaining)
    expect(page.locator('#city-clocks-empty')).to_be_visible()
    expect(clocks).to_be_hidden()
    page.reload()
    expect(clocks.locator('.clock-city')).to_have_count(0)


def city_clock_sort(browser):
    page = preview_page(browser)
    page.clock.install(time=datetime.fromisoformat('2026-10-03T16:29:45+00:00'))
    page.add_init_script("""localStorage.setItem('home-new-tab.city-clocks.v1', JSON.stringify([
      {name: 'Brisbane', lat: -27.47, lon: 153.03, zone: 'Australia/Brisbane'},
      {name: 'Adelaide', lat: -34.93, lon: 138.60, zone: 'Australia/Adelaide'},
      {name: 'St. John’s', lat: 47.56, lon: -52.71, zone: 'America/St_Johns'},
      {name: 'Caracas', lat: 10.48, lon: -66.88, zone: 'America/Caracas'},
      {name: 'Accra', lat: 5.60, lon: -0.19, zone: 'Africa/Accra'}
    ]));""")
    page.goto(f'{BASE}globe.html')
    clocks = page.locator('#clocks .clock-city')
    expect(clocks).to_have_text(['Caracas', 'St. John’s', 'Accra', 'Adelaide', 'Brisbane'])
    adelaide = page.locator('#clocks').get_by_role('button', name=re.compile('Adelaide'))
    adelaide.click()
    page.clock.fast_forward(30_000)
    expect(clocks).to_have_text(['Caracas', 'St. John’s', 'Accra', 'Brisbane', 'Adelaide'])
    expect(adelaide).to_be_focused()
    expect(adelaide).to_have_attribute('aria-pressed', 'true')
    page.close()


def clock_proposals(browser, errors, screenshots):
    for name in ('shoulders', 'inline'):
        for width, height in ((1440, 900), (390, 844), (320, 720)):
            page = preview_page(browser, viewport={'width': width, 'height': height}, timezone_id='Europe/Madrid')
            collect_errors(page, errors)
            assert page.goto(f'{BASE}globe-{name}.html').ok
            manual_weather(page)
            check(page, 'grid')
            clock = page.locator('.current-clock').bounding_box()
            date = page.locator('.date-block').bounding_box()
            globe = page.locator('#globe').bounding_box()
            assert date['x'] < clock['x']
            assert clock['y'] < globe['y']
            if width == 1440:
                expect(page.locator('#local-zone')).not_to_be_empty()
                status(page)
                screenshot(page, f'clock-{name}', screenshots)
                city_rotation(page)
            if width == 390:
                screenshot(page, f'clock-{name}-mobile', screenshots)
            page.close()


def theme_behavior(page):
    root = page.locator('html')
    page.emulate_media(color_scheme='light')
    expect(root).to_have_attribute('data-theme', 'light')
    page.locator('#settings-open').click()
    picker = page.locator('#theme')
    expect(picker).to_have_value('system')
    before = page.locator('#globe').evaluate('(el) => el.toDataURL()')
    page.emulate_media(color_scheme='dark')
    expect(root).to_have_attribute('data-theme', 'dark')
    page.wait_for_function('(before) => document.querySelector("#globe").toDataURL() !== before', arg=before)
    picker.select_option('light')
    expect(root).to_have_attribute('data-theme', 'light')
    picker.select_option('dark')
    page.emulate_media(color_scheme='light')
    expect(root).to_have_attribute('data-theme', 'dark')
    page.reload()
    expect(root).to_have_attribute('data-theme', 'dark')
    page.locator('#settings-open').click()
    expect(picker).to_have_value('dark')
    picker.select_option('system')
    expect(root).to_have_attribute('data-theme', 'light')
    page.keyboard.press('Escape')


COLOR_THEMES = ('gruvbox', 'deep-ocean', 'tokyo-night', 'dracula', 'oxblood', 'unit-01')


def palette_options(page):
    background = page.locator('body').evaluate('el => getComputedStyle(el).backgroundColor')
    page.locator('#settings-open').click()
    picker = page.locator('#theme')
    for name in COLOR_THEMES:
        picker.select_option(name)
        expect(page.locator('html')).to_have_attribute('data-theme', name)
        expect(page.locator('body')).not_to_have_css('background-color', background)
    page.keyboard.press('Escape')


def palette_persistence(page, peer):
    page.bring_to_front()
    globe = page.locator('#globe')
    previous = globe.evaluate('(el) => el.toDataURL()')
    page.locator('#settings-open').click()
    page.locator('#theme').select_option('tokyo-night')
    expect(peer.locator('html')).to_have_attribute('data-theme', 'tokyo-night')
    page.wait_for_function('(before) => document.querySelector("#globe").toDataURL() !== before', arg=previous)
    page.reload()
    expect(page.locator('html')).to_have_attribute('data-theme', 'tokyo-night')
    page.locator('#settings-open').click()
    expect(page.locator('#theme')).to_have_value('tokyo-night')
    page.keyboard.press('Escape')


def early_theme(browser):
    for system, saved, expected in (
        ('dark', 'system', 'dark'),
        ('light', 'tokyo-night', 'tokyo-night'),
        ('light', 'invalid', 'light'),
    ):
        page = preview_page(browser, color_scheme=system)
        page.add_init_script(f"localStorage.setItem('home-new-tab.theme.v1', '{saved}');")
        url = f'{BASE}globe.html'

        def early_markup(route):
            response = route.fetch()
            head, body = response.text().split('</head>', 1)
            route.fulfill(response=response, body=head + '</head>' + body.split('<script', 1)[0])

        page.route(url, early_markup)
        assert page.goto(url).ok
        expect(page.locator('html')).to_have_attribute('data-theme', expected)
        colors = page.evaluate('() => [document.documentElement, document.body].map(el => getComputedStyle(el).backgroundColor)')
        opposite = page.evaluate('''() => {
            const root = document.documentElement;
            root.dataset.theme = root.dataset.theme === 'light' ? 'dark' : 'light';
            return getComputedStyle(root).backgroundColor;
        }''')
        assert colors[0] == colors[1] and colors[0] != opposite, (system, saved, colors)
        page.close()


def stable_clock(browser):
    page = preview_page(browser, viewport={'width': 1440, 'height': 900}, timezone_id='Europe/Madrid')
    page.clock.install(time=datetime.fromisoformat('2028-03-01T09:59:45+01:00'))
    page.goto(f'{BASE}globe.html')
    readout = page.locator('#local-time')
    expect(readout).to_have_text('09:59 AM')
    wait_frame(page)
    assert 'IBM Plex Mono' in readout.evaluate('el => getComputedStyle(el).fontFamily')
    before = readout.bounding_box()
    date = page.locator('.date-block').bounding_box()
    page.clock.fast_forward(17_000)
    expect(readout).to_have_text('10:00 AM')
    assert readout.bounding_box() == before and page.locator('.date-block').bounding_box() == date
    page.close()


def geo_sun_regression(browser, errors):
    context = browser.new_context(timezone_id='Europe/Madrid',
        geolocation={'latitude': 41.3874, 'longitude': 2.1686, 'accuracy': 30}, permissions=['geolocation'])
    mock_providers(context)
    page = context.new_page()
    collect_errors(page, errors)
    page.clock.install(time=datetime.fromisoformat('2026-11-26T16:00:00+01:00'))
    with page.expect_request(lambda request: 'latitude=41.39' in request.url and 'longitude=2.17' in request.url, timeout=16000):
        assert page.goto(f'{BASE}globe.html').ok
    expect(page.locator('#place-name')).to_have_text('Near Barcelona')
    sun = page.locator('#sun-marker')
    countdown = page.locator('#night-progress')
    sunrise = page.locator('#sunrise')
    sunset = page.locator('#sunset')

    def cursor_x():
        return float(sun.get_attribute('transform').split()[0].removeprefix('translate('))

    def minutes_left():
        match = re.fullmatch(r'(?:(\d+)h )?(\d+)m to sunrise', countdown.inner_text())
        assert match
        return 60 * int(match[1] or 0) + int(match[2])

    expect(sun).to_have_attribute('data-state', 'day')
    expect(countdown).to_be_hidden()
    assert sunrise.bounding_box()['x'] < sunset.bounding_box()['x']
    page.clock.fast_forward(4 * 3_600_000)
    expect(sun).to_have_attribute('data-state', 'night')
    expect(sun).to_be_visible()
    expect(sun.locator('.sun-night-glyph')).to_be_visible()
    expect(sun.locator('.sun-halo')).to_be_hidden()
    assert sunset.bounding_box()['x'] < sunrise.bounding_box()['x']
    start_x = cursor_x()
    start_minutes = minutes_left()
    assert 20 < start_x < 160
    page.clock.fast_forward(3_600_000)
    assert cursor_x() > start_x
    assert abs(minutes_left() - (start_minutes - 60)) <= 1
    page.clock.fast_forward((3 * 60 - 1) * 60_000)
    before_midnight = cursor_x()
    bounds = (sunset.inner_text(), sunrise.inner_text())
    page.clock.fast_forward(2 * 60_000)
    expect(sun).to_have_attribute('data-state', 'night')
    assert 0 < cursor_x() - before_midnight < 2
    assert bounds == (sunset.inner_text(), sunrise.inner_text())
    page.clock.fast_forward(6 * 3_600_000)
    expect(sun).to_have_attribute('data-state', 'night')
    assert 240 < cursor_x() < 300
    page.clock.fast_forward(6 * 3_600_000)
    expect(sun).to_have_attribute('data-state', 'day')
    expect(countdown).to_be_hidden()
    expect(sun.locator('.sun-night-glyph')).to_be_hidden()
    expect(sun.locator('.sun-halo')).to_be_visible()
    assert sunrise.bounding_box()['x'] < sunset.bounding_box()['x']
    assert float(sun.get_attribute('transform').split()[1].strip(')')) < 78
    first = sun.get_attribute('transform')
    page.clock.fast_forward(3_600_000)
    expect(sun).not_to_have_attribute('transform', first)
    page.locator('#weather-place').click()
    page.locator('#city-query').fill('Longyearbyen')
    page.locator('#city-search button[type=submit]').click()
    page.get_by_role('button', name='Longyearbyen, Svalbard and Jan Mayen').click()
    expect(page.locator('#place-name')).to_have_text('Longyearbyen')
    expect(countdown).to_have_text('No complete solar cycle nearby')
    expect(sun).to_be_hidden()
    expect(sunrise).to_have_text('—')
    expect(sunset).to_have_text('—')
    manual_weather(page)
    page.reload()
    expect(page.locator('#place-name')).to_contain_text('Madrid')
    assert page.evaluate('localStorage.getItem("home-new-tab.location-mode.v1")') == 'manual'
    context.close()


def remember_preferences(browser, errors):
    context = browser.new_context(timezone_id='Europe/Madrid',
        geolocation={'latitude': 41.3874, 'longitude': 2.1686, 'accuracy': 30})
    mock_providers(context)
    page = context.new_page()
    collect_errors(page, errors)
    url = f'{BASE}globe.html'
    assert page.goto(url).ok
    expect(page.locator('#place-name')).to_have_text('Set location')
    page.locator('#weather-place').click()
    expect(page.locator('#geo-disclosure')).to_be_visible()
    context.grant_permissions(['geolocation'], origin=BASE)
    page.locator('#locate').click()
    expect(page.locator('#place-name')).to_have_text('Near Barcelona')
    page.locator('#settings-open').click()
    page.locator('#theme').select_option('tokyo-night')
    context.clear_permissions()
    context.add_init_script('window.locationReads = 0; navigator.geolocation.getCurrentPosition = () => window.locationReads++;')
    with page.expect_request(lambda request: 'latitude=41.39' in request.url and 'longitude=2.17' in request.url):
        page.reload()
        expect(page.locator('#place-name')).to_have_text('Near Barcelona')
    expect(page.locator('html')).to_have_attribute('data-theme', 'tokyo-night')
    assert page.evaluate('window.locationReads') == 0
    second = context.new_page()
    collect_errors(second, errors)
    assert second.goto(url).ok
    expect(second.locator('#place-name')).to_have_text('Near Barcelona')
    expect(second.locator('html')).to_have_attribute('data-theme', 'tokyo-night')
    manual_weather(second)
    assert second.evaluate('localStorage.getItem("home-new-tab.device-home.v1")') is None
    second.reload()
    expect(second.locator('#place-name')).to_have_text('Madrid')
    context.close()


def website_links(page):
    install = page.get_by_role('link', name='Install extension', exact=True)
    github = page.get_by_role('link', name='GitHub', exact=True)
    expect(install).to_have_attribute('href', re.compile(r'^https://chromewebstore\.google\.com/detail/[^/]+/pgeahicgbpcfobknhbgjhlldjpapbgol$'))
    expect(github).to_have_attribute('href', 'https://github.com/cris7ian/pale-blue-dot-tab')
    for link in (install, github):
        expect(link).to_be_visible()
        expect(link).to_have_attribute('target', '_blank')
        assert 'noopener' in link.get_attribute('rel').split()
    first, second = [link.bounding_box() for link in (install, github)]
    assert first['x'] + first['width'] <= second['x']
    if page.evaluate('innerWidth') <= 650:
        expect(page.locator('.masthead-left')).not_to_be_visible()
        footer = page.locator('.mobile-links').bounding_box()
        clocks = page.locator('#clocks').bounding_box()
        assert footer['y'] >= clocks['y'] + clocks['height']
        assert min(first['y'], second['y']) >= footer['y']
    else:
        expect(page.locator('.mobile-links')).not_to_be_visible()
        settings = page.locator('#settings-open').bounding_box()
        assert second['x'] + second['width'] <= settings['x']


def safari_install_link(browser, errors):
    mac = ('Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 '
           '(KHTML, like Gecko) Version/26.0 Safari/605.1.15')
    iphone = ('Mozilla/5.0 (iPhone; CPU iPhone OS 26_0 like Mac OS X) AppleWebKit/605.1.15 '
              '(KHTML, like Gecko) Version/26.0 Mobile/15E148 Safari/604.1')
    for user_agent, width, touches, show_install in (
        (mac, 1440, 0, False),  # Desktop masthead
        (mac, 500, 0, False),   # Footer in a narrow desktop window
        (mac, 1024, 5, True),   # iPad in desktop mode
        (iphone, 390, 5, True),
    ):
        page = preview_page(browser, user_agent=user_agent, viewport={'width': width, 'height': 900})
        collect_errors(page, errors)
        page.add_init_script(f"Object.defineProperty(navigator, 'maxTouchPoints', {{value: {touches}}});")
        assert page.goto(HOME).ok
        if show_install:
            website_links(page)
        else:
            expect(page.get_by_role('link', name='Install extension', exact=True)).to_have_count(0)
            expect(page.get_by_role('link', name='GitHub', exact=True)).to_be_visible()
            for link in page.locator('.masthead-link[data-primary]').all():
                expect(link).to_have_css('display', 'none')
        page.close()


def design_previews(browser, errors, screenshots):
    for design in DESIGNS:
        for width, height in ((1440, 900), (390, 844)):
            page = preview_page(browser, viewport={'width': width, 'height': height}, timezone_id='Europe/Madrid')
            collect_errors(page, errors)
            assert page.goto(f'{BASE}{design}.html?design={design}').ok
            manual_weather(page)
            check(page, design)
            screenshot(page, f'{design}-{width}', screenshots)
            page.close()
    leap_year(browser)
    type_proposal(browser, errors, screenshots)
    clock_proposals(browser, errors, screenshots)


def live_smoke(browser, url, errors):
    page = browser.new_page(timezone_id='Europe/Madrid')
    collect_errors(page, errors)
    assert page.goto(url).ok
    manual_weather(page)
    status(page)
    page.close()


def new_tab(context, errors):
    page = context.new_page()
    collect_errors(page, errors)
    try:
        page.goto('chrome://newtab/', wait_until='commit', timeout=12000)
    except Error as error:
        if 'ERR_ABORTED' not in str(error):
            raise
    page.wait_for_selector('#globe', timeout=15000)
    assert page.evaluate('location.protocol') == 'chrome-extension:'
    return page


def extension_checks(chromium, browser_args, errors):
    extension = str(HERE.parent / 'extension')
    with TemporaryDirectory(prefix='home-chrome-') as profile:
        with chromium.launch_persistent_context(profile, **browser_args, timezone_id='Europe/Madrid',
                args=[f'--disable-extensions-except={extension}', f'--load-extension={extension}']) as ctx:
            mock_providers(ctx)
            ctx.set_geolocation({'latitude': 41.3874, 'longitude': 2.1686, 'accuracy': 30})
            page = new_tab(ctx, errors)
            expect(page.locator('.masthead-link')).to_have_count(0)
            assert page.evaluate('Boolean(chrome.runtime.id)')
            assert page.evaluate('chrome.permissions.contains({permissions:["geolocation"]})')
            expect(page.locator('#place-name')).to_have_text('Set location')
            assert page.evaluate('localStorage.getItem("home-new-tab.location-mode.v1")') is None
            page.locator('#weather-place').click()
            page.locator('#locate').click()
            expect(page.locator('#place-name')).to_have_text('Near Barcelona')
            page.reload()
            expect(page.locator('#place-name')).to_have_text('Near Barcelona')
            ctx.set_geolocation(None)
            cached = new_tab(ctx, errors)
            expect(cached.locator('#place-name')).to_have_text('Near Barcelona')
            cached.close()
            manual_weather(page)
            check(page, 'grid')
            status(page)
            theme_behavior(page)
            page.locator('#settings-open').click()
            page.locator('#settings summary').click()
            expect(page.get_by_role('link', name='Open-Meteo', exact=True)).to_be_visible()
            page.keyboard.press('Escape')
            second = new_tab(ctx, errors)
            expect(second.locator('#place-name')).to_contain_text('Madrid')
            palette_persistence(second, peer=page)
            globe_focus(second)
            configurable_clocks(second, peer=page)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--chromium', type=Path)
    parser.add_argument('--proposals', action='store_true', help='Check alternate design previews and their year grid')
    parser.add_argument('--screenshots', action='store_true', help='Save layout screenshots into experiments/artifacts')
    parser.add_argument('--live', nargs='?', const=HOME, metavar='URL', help='Also check live weather, city search, and ISS')
    args = parser.parse_args()
    browser_args = {'executable_path': str(args.chromium)} if args.chromium else {'channel': 'chromium'}
    errors = []
    with sync_playwright() as p:
        browser = p.chromium.launch(**browser_args)
        try:
            website_layout(browser, errors, args.screenshots)
            safari_install_link(browser, errors)
            early_theme(browser)
            stable_clock(browser)
            geo_sun_regression(browser, errors)
            remember_preferences(browser, errors)
            city_clock_sort(browser)
            print('Website: responsive layout, themes, globe, solar transitions, and clock reordering')
            if args.proposals:
                design_previews(browser, errors, args.screenshots)
                print('Alternate design previews and leap-year grid passed')
            if args.live:
                live_smoke(browser, args.live, errors)
                print(f'Live city search, weather, and ISS passed: {args.live}')
        finally:
            browser.close()
        extension_checks(p.chromium, browser_args, errors)
        print('Chrome extension: new-tab override, location opt-in, focus, and cross-tab settings')
    assert not errors, errors


if __name__ == '__main__':
    main()
