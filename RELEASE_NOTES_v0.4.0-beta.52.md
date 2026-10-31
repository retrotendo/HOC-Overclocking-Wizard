# HOC Undervolting Wizard v0.4.0-beta.52

UI cleanup for the final guide pages.

- Split the Real-World Stability Check into two clear full-width pages.
- Page 1 focuses only on how to perform the real-world confirmation with The Legend of Zelda: Tears of the Kingdom for at least one hour.
- Page 2 explains what to do if instability appears and keeps the troubleshooting order explicit: Low VMIN -> VDDQ -> VDD2 -> CPU High UV -> CPU Low UV.
- Troubleshooting continues to enforce the one-setting-at-a-time rule: change one step, test again, restore the previous value if the failure remains, then try the next setting.
- Reworked the Complete page into a compact centered two-column summary so labels and final values stay visually together.
- The final page now shows: `Saved to Performance Modes · Battery Mode`.
- No tuning limits, voltage search behavior, stability-test durations or safety-state guard logic were changed.
