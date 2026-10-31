# HOC Undervolting Wizard v0.4.0-beta.45

## Startup hotfix
- Fixes a beta44 regression that could leave the app visually stuck on `Checking for updates...` after the update check completed.
- The cause was an accidental recursive fallback in `uiPresent()` before the graphical framebuffer had been initialized.
- Before GUI initialization, screen updates now correctly use the existing libnx console renderer.
- After the warning is accepted and the graphical backend initializes, the beta44 1280x720 GUI is used as intended.

## No tuning changes
- Tuning thresholds, search logic, recovery behavior, validation durations and stress-test logic are unchanged from beta44.
