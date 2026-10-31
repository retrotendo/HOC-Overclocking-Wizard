# v0.4.0-beta.37

Consistent automatic stability-test flow.

- Validation pages now use the same layout: objective, current tuned value, test description, then actions.
- Temporary Override details are hidden from normal test pages.
- `A : Start automatic stability test` now sets the required CPU/GPU/RAM Temporary Overrides automatically, verifies them, runs the test, and restores the previous overrides afterwards.
- If automatic test-clock setup fails, a dedicated error page appears with Retry instead of asking the user to configure overrides manually.
- VDDQ and VDD2 keep the intended search flow: each candidate runs a 1-minute RAM test; continue downward until the first FAIL/crash, then restore the last passing value and confirm it with a 1-hour RAM test.
- VDDQ/VDD2 validation pages show the value being tested and the currently active Horizon OC voltage.
- Built-in test pages consistently provide `+ : Known PASS / Skip step` and `X : Known FAIL / Skip step`.
- Real-world validation also offers `+ : Known PASS / Skip step`.
