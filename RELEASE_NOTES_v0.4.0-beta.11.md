# HOC Undervolting Wizard v0.4.0-beta.11

This beta hardens the in-app updater after beta.9 could silently ignore an update-check failure.

## Updater reliability

- Add a lightweight public `UPDATE.txt` manifest in the repository as a second update metadata source.
- Keep the GitHub Releases API as a fallback.
- Compare both sources and use the newest valid version found.
- Send no-cache headers for update metadata requests.
- Show update-check errors on screen instead of silently continuing.
- Add `A = Retry` and `B = Continue current version` on update-check errors.

## No tuning changes

The beta.10 tuning/test behavior and right-side Ultrahand-friendly UI remain unchanged.

This remains a pre-release until validated on real hardware.
