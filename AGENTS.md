# Pale Blue Dot Tab

- Build and test with the commands in `README.md`, including the Chrome new-tab override.
- Pushes to `main` deploy the site and privacy policy. The production `public/` directory is live; never build previews into it. See `docs/production.md`.
- Chrome requires `geolocation` under `permissions`. Read device location only after in-app opt-in, and keep the disclosure and privacy policy aligned.
- Manual-install and Chrome Web Store ZIPs use different layouts. A GitHub release does not submit a Store update.
- The Safari app in `safari/` copies `extension/` at build time and writes its own manifest. Keep its version equal to the manifest's.
