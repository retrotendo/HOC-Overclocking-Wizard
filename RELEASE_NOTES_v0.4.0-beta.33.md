# v0.4.0-beta.33

UI consistency and wording cleanup for the guided tuning flow.

- Preparation now starts with `Set these values:` below the header separator.
- Removed the blank line between `@ HOC Toolkit` and the CPU Boost value.
- Moved the normal Wizard reset hint to the top-right of the header and removed duplicate bottom reset labels.
- Simplified Automatic Setting by removing internal `SetConfigValues / Save KIP` and readback wording.
- Simplified reboot guidance to `Reboot is required to apply settings.` and removed KIP wording from the recovery instructions.
- The normal-CFW boot/freeze/crash warning is now red.
- Setting screens now use the same layout: Objective -> Set value(s) -> Horizon OC -> setting -> actions.
- CPU Low UV Boot Search now clearly states the objective: find the highest Low UV that can boot normally.
- CPU Low VMIN uses the matching boot-search layout and objective.
- VDDQ, VDD2, and High UV setting pages use the same layout principle.
- Renamed `Known PASS / Skip` on setting pages to `Skip to next value`.
- No tuning algorithms, boot-search decisions, voltage scanning, or stress-test logic changed.
