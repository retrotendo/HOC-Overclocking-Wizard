# HOC Undervolting Wizard v0.4.0-beta.44

## Real graphical interface
- Replaces the ANSI / ASCII console-style Wizard shell with a true 1280x720 framebuffer interface.
- Uses the Nintendo Switch shared system font through FreeType for clean proportional text.
- Implements the approved minimal dark design with real rounded cards, spacing, typography and accent colors.
- Adds the top progress path for Baseline, Low UV, Low VMIN, VDDQ, VDD2, High UV and Finalize.
- The active progress step has a subtle visual pulse.

## Guided layout
- The left side contains the existing Wizard instructions and controller actions inside the main guided-tuning card.
- The requested value is not duplicated in a separate left-side chooser.
- The upper-right Current Instruction card shows the exact Horizon OC setting currently requested by the Wizard.
- The lower-right Actual Active Values card continuously shows CPU Low UV, CPU Low VMIN, VDDQ, VDD2 and CPU High UV.
- If an active value disagrees with the setting currently requested by the Wizard, that active value is highlighted in red.
- Actions are rendered as real color-coded UI buttons instead of terminal background-color rows.

## Graphical stress tests
- Built-in 1-minute, 30-minute and 1-hour tests now use the same graphical interface.
- Test progress, elapsed time, CPU/RAM counters, errors and mismatches are displayed graphically.

## Tuning logic retained
- The complete v0.4.0-beta.43 / beta42 tuning, validation, recovery and limit-confirmation behavior is retained.
- No tuning thresholds, search directions, validation durations or pass/fail logic were changed for this UI release.
- The startup update check and risk warning remain before graphical initialization so update/recovery messages remain available even if the graphics backend cannot start.
