# Future Professional Installer (Phase 3)

## Overview
To provide the most seamless user experience, Hive should eventually move from a "Portable Folder" to a "Professional Installer" (e.g., Inno Setup or NSIS).

## Benefits
1. **Silent Firewall Setup:** Rules are created during installation while the user has already granted UAC permission.
2. **Standard Installation:** Hive is placed in `C:\Program Files\Hive` and gets a proper Start Menu shortcut.
3. **Clean Uninstallation:** Removing the app automatically cleans up firewall rules and registry keys.
4. **Defender Trust:** Installed applications are generally viewed more favorably by heuristic scanners than portable executables.

## Inno Setup Strategy
An Inno Setup `.iss` script should:
- Target `dist/Hive/*` as the source.
- Use `[Run]` section to execute firewall setup:
  ```pascal
  Filename: "{app}\setup-hive.ps1"; Parameters: "-ExecutionPolicy Bypass"; Flags: runhidden
  ```
- Use `[UninstallRun]` to clean up:
  ```pascal
  Filename: "{app}\remove-hive.ps1"; Parameters: "-ExecutionPolicy Bypass"; Flags: runhidden
  ```

## Current Status
Implementation of Phase 2 (In-App Auto-Elevation) is the current standard. This document serves as the roadmap for the transition to a full installer when the project reaches production-ready status.
