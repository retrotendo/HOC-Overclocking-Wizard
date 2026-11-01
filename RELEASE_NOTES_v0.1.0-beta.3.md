# HOC Overclocking Wizard v0.1.0-beta.3

- Fixed startup update checking being skipped because the socket service was initialized twice.
- The updater now uses the network service already owned by the main application and no longer shuts it down itself.
- Corrected remaining updater labels from HOC Undervolting Wizard to HOC Overclocking Wizard.
- Includes all beta2 changes: 100% battery requirement, Expected Max OC on hardware detection, and context-aware Active Values.
