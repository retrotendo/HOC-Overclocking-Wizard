# HOC Undervolting Wizard v0.4.0-beta.40

## Validation flow
- VDDQ search still uses 1-minute RAM screening per candidate.
- Final VDDQ now gets a 30-minute RAM validation while VDD2 remains on its known-safe value.
- VDD2 search still uses 1-minute RAM screening per candidate.
- After VDD2 is found, the final VDDQ + VDD2 pair is validated together for 1 hour at the Boost RAM state.
- The critical handheld anchor remains a 1-hour CPU memtester run at 1020 / 384 / 1331.
- High UV search still uses 1-minute screening per candidate.
- The final High UV value is validated for 1 hour with CPU memtester at 1785 / 76.8 / 1600.
- A separate 1-hour Combined CPU + RAM test follows at 1785 / 76.8 / 1600.
- Real-world Tears of the Kingdom, loading, Home and Sleep/Wake validation remains the final step.

## Startup warning
- Added a risk/liability warning immediately after the update check and before Hardware Detection or tuning.
- The warning explicitly mentions crashes, boot failures, save/data corruption or loss and possible hardware damage.
- Continuing requires explicit confirmation with A; B exits the Wizard.
