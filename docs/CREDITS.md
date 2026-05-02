# Hive: Credits & Acknowledgments

## Core Inspirations

### FlyingCarpet
- **Author:** Theron Spiegl
- **Repository:** https://github.com/spieglt/FlyingCarpet
- **License:** GPL-3.0
- **Contribution:** Pioneered cross-platform WiFi Direct file transfer. Proved 200-250 Mbps speeds are achievable with proper TCP optimization. Our Windows and Linux implementations learned from their architecture.

### FlyingCarpet - wifidirect-legacy-ap
- **Repository:** https://github.com/spieglt/wifidirect-legacy-ap
- **License:** GPL-3.0
- **Contribution:** Rust adaptation of Microsoft's WiFi Direct Legacy AP sample. Provided valuable insights for Windows WiFi Direct implementation.

### LocalSend
- **Repository:** https://github.com/localsend/localsend
- **License:** MIT
- **Contribution:** Excellent file transfer protocol design and cross-platform architecture patterns.

---

## WiFi Direct & P2P Libraries

### Wifi-Direct-on-Linux
- **Author:** NaniteFactory
- **Repository:** https://github.com/NaniteFactory/Wifi-Direct-on-Linux
- **License:** Not specified (research/educational use)
- **Contribution:** Provided working `wpa_supplicant` command sequences for Linux P2P group creation and connection.

### Wroup
- **Author:** ble180
- **Repository:** https://github.com/ble180/Wroup
- **License:** Apache 2.0
- **Contribution:** Android WiFi Direct library with clean server/client architecture that informed our design patterns.

### react-native-wifi-p2p
- **Author:** Kirill Zyusko
- **Repository:** https://github.com/kirillzyusko/react-native-wifi-p2p
- **License:** MIT
- **Contribution:** React Native WiFi P2P bindings, useful reference for mobile implementation patterns.

---

## System Libraries & APIs

### wpa_supplicant
- **Project:** Wi-Fi Protected Access client and IEEE 802.11 authentication
- **Website:** https://w1.fi/wpa_supplicant/
- **License:** BSD / GPL-2.0
- **Contribution:** Industry-standard WiFi management daemon for Linux. Core component enabling all Linux P2P functionality.

### Microsoft Windows Runtime (WinRT)
- **Vendor:** Microsoft Corporation
- **License:** Proprietary (public APIs)
- **Contribution:** WiFi Direct APIs (`Windows.Devices.WiFiDirect`) enabling modern P2P connections on Windows 10/11.

### windows-rs
- **Repository:** https://github.com/microsoft/windows-rs
- **License:** MIT / Apache 2.0
- **Contribution:** Rust bindings for Windows APIs. Referenced for understanding WinRT API usage patterns.

---

## Development Tools & Libraries

### nlohmann/json
- **Author:** Niels Lohmann
- **Repository:** https://github.com/nlohmann/json
- **License:** MIT
- **Contribution:** Single-header JSON library for C++. Used for all JSON parsing and generation in agents.

### D-Bus
- **Project:** freedesktop.org
- **Website:** https://www.freedesktop.org/wiki/Software/dbus/
- **License:** AFL-2.1 / GPL-2.0
- **Contribution:** Inter-process communication used for Linux wpa_supplicant integration.

---

## Documentation & Research

### WiFi Direct Protocol Specifications
- **Source:** Wi-Fi Alliance
- **Website:** https://www.wi-fi.org/discover-wi-fi/wi-fi-direct
- **Contribution:** Official WiFi Direct (P2P) technical specifications and certification requirements.

### Microsoft WiFi Direct Documentation
- **Source:** Microsoft Learn
- **Links:**
  - https://learn.microsoft.com/en-us/uwp/api/windows.devices.wifidirect
  - https://github.com/microsoft/Windows-universal-samples (WiFiDirectLegacyAP sample)
- **Contribution:** Official Windows WiFi Direct API documentation and sample code.

### wpa_supplicant P2P Documentation
- **Sources:**
  - https://w1.fi/wpa_supplicant/devel/p2p.html
  - Murata Manufacturing P2P examples
  - Raspberry Pi Forums P2P discussions (2024)
- **Contribution:** Real-world examples of P2P group creation, connection, and configuration.

---

## Performance Optimization Research

### TCP Buffer Optimization
- **Sources:** Multiple networking performance papers and forums
- **Key Finding:** 4 MB send/receive buffers + TCP_NODELAY enables 200-250 Mbps over WiFi Direct
- **Contribution:** Proven socket configuration for maximum throughput.

---

## Testing & Validation

### Real-World Hardware Testing
- **Devices Tested:** Windows 10/11 laptops, Linux desktops/laptops, various WiFi adapters
- **Contribution:** Community feedback and bug reports helped identify critical issues (passphrase bug, device_address vs UUID bug).

---

## License Compatibility

This project respects all upstream licenses:

- **GPL-3.0 Projects:** Used for research and pattern learning. Where GPL code may be directly used, Hive can be dual-licensed as MIT/GPL at user's choice.
- **MIT Projects:** Code patterns and protocols freely incorporated with attribution.
- **Apache 2.0 Projects:** Architectural patterns adopted with appropriate credit.
- **Proprietary APIs:** Only public APIs used, no reverse engineering or unauthorized access.

---

## Special Thanks

- **Theron Spiegl** for creating FlyingCarpet and proving WiFi Direct file transfer is practical and fast.
- **LocalSend team** for demonstrating excellent cross-platform file transfer UX.
- **wpa_supplicant maintainers** for decades of WiFi management excellence.
- **The open-source community** for sharing knowledge, code, and solutions.
