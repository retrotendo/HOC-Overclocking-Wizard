# HOC Undervolting Wizard v0.4.0-beta.8

This beta adds an opt-in **startup self-updater** so future development builds can be installed directly from the Switch without repeatedly removing the SD card.

## Startup update check

In Full Application Mode the Wizard checks its own GitHub releases before loading tuning state.

- If the installed build is current, startup continues normally.
- If a newer build is available, the Wizard asks first:
  - **A** — Download & install
  - **B** — Not now; continue the currently installed build
- Network or update-check errors are non-fatal and simply continue the installed build.
- Applet Mode remains blocked before any network/update activity.

## Safe self-replacement

The updater does not overwrite the running NRO immediately.

1. Download the new `HOC-Undervolting-Wizard.nro` to a temporary `.new` file.
2. Download the matching release `.sha256` file.
3. Verify the downloaded NRO with libnx SHA256.
4. Rename the currently installed NRO to `.bak`.
5. Move the verified `.new` NRO into the original path.
6. If replacement fails, restore the old NRO.
7. Exit the Wizard. Relaunch from hbmenu to run the new build.

The updater uses the actual hbloader `argv[0]` NRO path when available and falls back to the standard Wizard path.

No GitHub token or credentials are embedded in the NRO. The repository therefore needs to be public for anonymous in-app update checks.

**beta.8 itself must be installed manually once. Future beta builds can then be installed in-app.**

All beta.7 tuning, Full Application Mode, HOC preflight, dynamic Low VMIN and known-result logic remains unchanged.

This remains a pre-release until validated on real Mariko / Switch OLED hardware.
