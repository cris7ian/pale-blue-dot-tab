# Pale Blue Dot Tab

A quieter new tab, with a view of the world. Pale Blue Dot Tab brings together an interactive globe, world clocks, weather, sunrise and sunset, and the Moon’s current phase. Follow the International Space Station, explore a city, or make the dashboard your own with your favorite clocks and theme.

![Globe-first dashboard with local weather, Moon and world clocks](docs/preview.png)

[Try Pale Blue Dot Tab in your browser](https://home.salsaparapizza.com/) · [Add to Chrome](https://chromewebstore.google.com/detail/home-new-tab/pgeahicgbpcfobknhbgjhlldjpapbgol) · [Privacy policy](https://home.salsaparapizza.com/privacy.html)

## Use as your homepage and new tab in Safari on Mac

No extension is needed.

1. In Safari, choose **Safari → Settings → General**.
2. Enter `https://home.salsaparapizza.com/` in the **Homepage** field.
3. Set **New windows open with** to **Homepage**.
4. Set **New tabs open with** to **Homepage**.

See [Apple’s Safari homepage guide](https://support.apple.com/guide/safari/ibrw1020/mac) for more details.

## Install in Chrome

[Add Pale Blue Dot Tab from the Chrome Web Store](https://chromewebstore.google.com/detail/home-new-tab/pgeahicgbpcfobknhbgjhlldjpapbgol). Chrome installs the extension and keeps it updated.

To install a build from GitHub instead, use the manual steps below.

### Manual install from GitHub

1. Open the [release](https://github.com/cris7ian/pale-blue-dot-tab/releases/tag/v1.1.0) while signed in to GitHub.
2. Download `pale-blue-dot-tab-v1.1.0.zip` and extract it to a folder you plan to keep.
3. Open `chrome://extensions`, enable **Developer mode**, and select **Load unpacked**.
4. Select the extracted `extension` folder.
5. Open a new tab and select **Keep it** if Chrome asks.

To update a manual installation, replace the files in the same folder and select **Reload** in `chrome://extensions`.

Choose a city for its weather and solar times, or select **Use my location** to use your device location. Chrome may show a location permission warning during installation, but the extension does not read your location until you opt in. Weather, city search, and live ISS positions need an internet connection. No account or API key is needed to use the extension.

Open **Settings → Theme** to choose System, Light, Dark, or one of six color palettes: Gruvbox, Deep Ocean, Tokyo Night, Dracula, Oxblood, and Unit‑01. The website and extension each save your theme and location in your browser. After you choose **Use my location**, the last approximate location is available even without a fresh reading. Choose a city to remove the saved device location. Settings do not sync between the website and extension.

## Develop

Build the extension and start a local preview:

```sh
python3 experiments/build_globe.py
python3 -m http.server 4174 --bind 127.0.0.1 --directory experiments/preview-local
```

Open [localhost:4174/globe.html](http://localhost:4174/globe.html). With the preview server running, run the tests with:

```sh
python3 -m unittest discover -s experiments
uv run --with playwright python experiments/verify_globe.py --chromium /path/to/chromium
```

The browser tests cover the shipped web layout and the Chrome new-tab override. They mock weather, city search, and ISS by default. Add `--proposals` to check alternate layouts, `--screenshots` to save images, or `--live [URL]` to check the live providers against the local preview or a deployed page.

For hosting and release details, see [production](docs/production.md).

## Credits

- [Natural Earth](https://www.naturalearthdata.com/downloads/10m-cultural-vectors/timezones/) for map boundaries (public domain).
- [Open-Meteo](https://open-meteo.com/) for weather and place search, and [Where the ISS at?](https://wheretheiss.at/) for ISS positions.
- [GeoNames cities5000](https://download.geonames.org/export/dump/) ([CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)) for nearby place labels. The bundled extract retains names and simplified coordinates.
- [Astronomy Engine](https://github.com/cosinekitty/astronomy) 2.1.19 (MIT) for solar events and lunar phases.
- [NASA’s Scientific Visualization Studio](https://svs.gsfc.nasa.gov/5001/) for the Moon mosaic, resized and contrast-adjusted.
- [Barlow Condensed](https://fonts.google.com/specimen/Barlow+Condensed) and [IBM Plex Mono](https://fonts.google.com/specimen/IBM+Plex+Mono), under the SIL Open Font License.
