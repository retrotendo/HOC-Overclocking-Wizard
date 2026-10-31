# HOC Undervolting Wizard v0.4.0-beta.12

This beta cleans up the user-facing Battery guide without changing the tuning or stress-test logic.

## Clear Horizon OC menu grouping

Every value the user must set is now grouped under the menu area where it belongs:

- **General**
- **RAM Settings**
- **CPU Settings**
- **CPU UV**
- **HOC Toolkit**
- **Temporary Overrides**

This makes the right-side Wizard panel easier to follow while the Ultrahand / Horizon OC overlay remains open on the left.

## No manual save prompts

Manual `Save KIP` / `Save Toolkit` instructions have been removed from the active Wizard flow. Where a persistent setting change requires it, the Wizard simply tells the user to **Reboot CFW**.

Recovery screens are also simplified: restore the previous value in the named Horizon OC menu and reboot CFW.

## Updater fallback

The GitHub Releases API fallback now scans up to 100 releases instead of only 5. The lightweight public `UPDATE.txt` manifest introduced in beta.11 remains the primary update source.

## No tuning changes

The beta.11 tuning order, voltage steps, VMIN detection, stress tests, KNOWN PASS/FAIL shortcuts, override checks and crash/reboot recovery logic are unchanged.

This remains a pre-release until validated on real hardware.
