# HOC Undervolting Wizard v0.4.0-beta.51

Safety-state guard on top of the beta50 UI cleanup.

- ACTUAL ACTIVE VALUES now compares all five tunable settings against the complete current Wizard state on every guide page, not only the setting being changed.
- The expected state follows either the Wizard's recommended baseline or the values imported with **Use my current settings as baseline**, then follows each last-known-good value as tuning progresses.
- The one value the Wizard currently asks the user to change is treated as the intended target; unrelated deviations are highlighted red immediately.
- Before automatic voltage scans, automatic region validation and every built-in stability/validation test, the Wizard verifies that all five tunable settings still match the expected state.
- Immediately before a reboot, the Wizard performs the same all-domain safety check so an accidental second change cannot be carried into the next boot.
- If a mismatch is found, the Wizard blocks progression with **Unexpected setting change**, asks the user to restore the red values, and only continues after a successful re-check.
- Includes all beta50 changes: full-width Real-World/Result pages, concise Tears of the Kingdom stability recommendation, and improved graphical text wrapping.
- No voltage-search limits, test durations, stress-test algorithms or tuning progression logic were changed.
