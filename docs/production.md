# Production

## Hosting

[home.salsaparapizza.com](https://home.salsaparapizza.com/) is served by Caddy. The deployment directory is configured in the [workflow](../.github/workflows/ci.yml).

**The production `public/` directory is live.** Do not build previews into it or run the legacy `build.py` in the production checkout. The current `experiments/build_globe.py` writes to `extension/` and `experiments/preview-local/` instead.

## Website deployment

Pushes to `main` trigger [CI and deploy](../.github/workflows/ci.yml). Pull requests run checks but do not deploy. After the checks pass, a self-hosted runner publishes `experiments/preview-local/globe.html` as `index.html` and `experiments/store/privacy.html` as `privacy.html`. The workflow skips publication if a newer `main` commit exists.

To redeploy the current `main`, use **CI and deploy → Run workflow** in GitHub Actions, or run:

```sh
gh workflow run ci.yml --ref main
```

After the workflow succeeds, check the deployed commit over public HTTPS:

```sh
curl -fsS https://home.salsaparapizza.com/deployment.json
```

Compare its `commit` with the intended `main` commit. The website workflow does not publish Chrome extension releases.

## Chrome extension releases

The published listing is [Add to Chrome](https://chromewebstore.google.com/detail/home-new-tab/pgeahicgbpcfobknhbgjhlldjpapbgol). The website links to this listing and to the repository in the desktop masthead and mobile footer. Safari on Mac shows only the repository link. The README includes Safari homepage setup and manual Chrome installation.

The manual-install ZIP contains an `extension/` folder. The Chrome Web Store ZIP has `manifest.json` at its root. A GitHub release does not upload or submit a Store update.

To prepare a Store package and screenshots from a committed release:

```sh
uv run --with playwright --with pillow python experiments/store/prepare.py \
  --ref v1.2.0 --out experiments/artifacts/store-v1.2.0 \
  --chromium /path/to/chromium
```

Upload the Store ZIP to the existing listing in the Developer Dashboard and submit it for review separately. Do not create a new listing for a name change.
