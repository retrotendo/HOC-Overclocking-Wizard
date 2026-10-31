# HOC Undervolting Wizard v0.4.0-beta.42

## Consistent Wizard limit handling
- All tuning searches now stop on an explicit `Wizard search limit reached` page before moving into validation.
- This applies to the Low UV maximum, Low VMIN minimum, VDDQ minimum, VDD2 minimum and High UV maximum.
- The notice is shown both when `Use my current settings as baseline` already starts at the Wizard boundary and when the normal search reaches that boundary.
- When a boundary is reached during active VDDQ, VDD2 or High UV tuning, the boundary candidate still runs its normal 1-minute quick stability test first. Only a passing candidate is then shown as the reached Wizard limit.
- Baselines already at the VDDQ or VDD2 minimum show the notice before the corresponding final validation begins.
- Low VMIN retains the 570 mV warning that going lower is not recommended because very low VMIN values may cause Sleep / Standby / Wake problems.
- The limit-notice state is persisted, so exiting and reopening the Wizard cannot silently skip the notice.
- While a limit notice is open, normal search keys are blocked; only explicit confirmation advances the Wizard.

## Existing validation flow retained
- VDDQ final validation remains 30 minutes.
- Final VDDQ + VDD2 pair validation remains 1 hour.
- Handheld 1020 / 384 / 1331 validation remains 1 hour.
- High UV CPU memtester and the separate Combined CPU + RAM validation remain 1 hour each.
- Startup risk/liability warning remains in place.
