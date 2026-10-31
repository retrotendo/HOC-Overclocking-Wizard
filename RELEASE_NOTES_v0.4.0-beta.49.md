# HOC Undervolting Wizard v0.4.0-beta.49

UX consistency pass for validation and test screens.

- Validation/result pages now follow the same rule used across the guide: left side explains the result/context, right side tells the user what to do next.
- CPU Low UV / Low VMIN voltage-region pages are shorter and more readable.
- Region rows are rendered compactly so several voltage regions fit without colliding with the action buttons.
- Right-side task card now says **Start the validation test** instead of repeating **CPU voltage scan** after the scan has already completed.
- Validation actions use explicit wording such as **Known PASS / Skip validation test**.
- Candidate tests distinguish **stability test** from longer **validation test** steps.
- VDDQ, VDD2, High UV, CPU/RAM integration and final validation pages use shorter, task-focused descriptions.
- Real-world validation uses **Known PASS / Skip real-world test**.
- No tuning values, search logic, recovery behavior or stress-test implementation were changed in this release.
