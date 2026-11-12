# Hardware Setup & Antenna Engineering Guide

## 1. ESP32-S3 Board Selection & RF Considerations
For high-sensitivity RF sensing (where phase changes under $5^\circ$ are measured), hardware selection and antenna engineering directly impact performance.

### Recommended Boards:
- **ESP32-S3-WROOM-1 / DevKitC-1 (N8R2 / N16R8):** Dual-core Xtensa LX7 @ 240 MHz with Vector Instructions (ESP-NN) and hardware floating-point acceleration.
- **External Antenna Edition (ESP32-S3-WROOM-1U):** Features an IPEX / U.FL connector. Replacing the omnidirectional PCB trace antenna with a high-gain ($5\text{ dBi}$) directional patch or dipole antenna increases sensing range through drywall from $3.5\text{ m}$ to over $7.0\text{ m}$.

---

## 2. Power Supply Noise Mitigation
Wi-Fi CSI phase measurements are sensitive to local voltage ripple on the analog radio power rails (VDD33).
- **Symptom of Dirty Power:** 60 Hz / 120 Hz hum appearing in the Doppler spectrogram when powered by cheap USB chargers or laptop switching supplies under heavy CPU load.
- **Hardware Fix:** Solder a $100\ \mu\text{F}$ electrolytic capacitor in parallel with a $0.1\ \mu\text{F}$ ceramic capacitor across the `5V` (or `3V3`) and `GND` pins on the ESP32-S3 development board. This suppresses switching transients and stabilizes oscillator phase noise.

---

## 3. Wi-Fi Channel Selection & Co-Channel Hygiene
2.4 GHz ISM band congestion will degrade CSI packet reception if neighboring access points occupy overlapping frequencies.

| Channel | Center Frequency | Recommended Use |
| :--- | :--- | :--- |
| **Channel 1** | 2.412 GHz | Clean if lower band is unoccupied |
| **Channel 6** | 2.437 GHz | **Standard Default** for mobile hotspots (`Alkindi`) |
| **Channel 11** | 2.462 GHz | Cleanest in heavily congested enterprise environments |

> [!IMPORTANT]
> Always lock both the Phone Hotspot and the ESP32 firmware to the exact same fixed channel. Auto-channel switching by the host router will break the continuity of the phase history.
