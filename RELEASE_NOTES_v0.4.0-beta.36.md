# v0.4.0-beta.36

Boot-search recovery and test-flow cleanup.

- Simplified the successful Low UV / Low VMIN boot-check screen by removing redundant requested-value status text.
- Simplified recovery detection: the Wizard now directly states which requested Low UV / Low VMIN appears not to have booted and shows the proposed last-good value.
- `X : Try one safer value` moves the proposed last-good value one additional safe step (Low UV -1, Low VMIN +10 mV) before confirmation.
- If an additionally safer recovery value is confirmed, the Wizard applies it and requires a reboot before continuing.
- Crash guidance is shown directly under test-start actions.
- Test-start pages provide `+ : Known PASS / Skip step`.
- On Boot Search setting pages, `+ : Known stable / Skip to next value` only advances the candidate; it does not open the setting-check page or reboot. `A : Check setting` remains the explicit check/apply action.
- Low UV / Low VMIN candidates that are checked or set are forced through the reboot flow before they can be evaluated as boot-stable.
