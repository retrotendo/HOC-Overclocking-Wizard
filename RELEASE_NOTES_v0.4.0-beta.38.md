# v0.4.0-beta.38

Known-unstable action on search pages.

- Boot/search setting pages now consistently show both directions: `+ : Known stable / Skip to next value` and `X : Known unstable / Use last good value`.
- `X` uses the existing FAIL/recovery path: the current candidate is treated as unstable and the previous last-known-good value is used for the following validation/long-test flow.
- No other tuning or stability-test logic was changed from beta37.
