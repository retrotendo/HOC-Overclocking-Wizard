# HOC Undervolting Wizard v0.4.0-beta.10

This beta fixes the right-side UI placement introduced in beta.9 after validation on a real Switch OLED.

## UI position fix

- Move the compact Wizard panel from console column 82 to column 36.
- Keep the panel directly to the right of the Ultrahand overlay.
- Shorten divider lines and the override-error table so text does not wrap at the right edge.
- Keep the same compact layout for preparation, tuning stages, final validation and blocked-override screens.

## Compatibility

The layout uses the Switch handheld 1280x720 logical output, so the same console-column placement applies to Switch OLED, standard Switch and Switch Lite. The tuning guide itself remains Mariko-focused.

## No tuning-logic changes

The beta.9/beta.8 behavior is retained unchanged:

- startup self-updater
- Full Application Mode requirement
- tuning order and voltage steps
- Save KIP / reboot points
- CPU/GPU/RAM override preflight
- dynamic Low VMIN floor detection
- CPU / RAM / Combined / GPU stress tests
- KNOWN PASS / FAIL shortcuts
- crash/reboot recovery

This remains a pre-release until validated on real hardware.