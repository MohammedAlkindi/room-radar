# room-radar

## What it does
Experiments in sensing people in a room without a camera, using ESP32 boards. The first track reads Wi-Fi Channel State Information (CSI) from one to five ESP32-S3 nodes and tries to detect presence, breathing and movement from how the radio channel changes. The second track reads an HLK-LD2450 24 GHz mmWave sensor over UART, which reports target positions directly.

## Status
Unfinished. The Wi-Fi CSI track detects that something moves but was never accurate in the room it was built in: it reported walking while the person sat still and counted two people when there was one, with one node and with five. The mmWave firmware is written but untested against hardware, because the LD2450 sensor had not arrived when work stopped on 2026-11-08. Treat every number in `docs/` as a target, not a measurement.

## Architecture
- `firmware/` holds one Arduino sketch per role: `esp32s3_csi_node` (single node, serial output at 20 Hz), `esp32_beacon` and `esp32_direct_radar` (a two-board transmit and receive pair), `esp32_mesh_node` and `esp32_master_receiver` (three to five nodes over ESP-NOW, one board on the laptop), and `mmwave_hlk_ld2450` (ESP32-S3 reading the LD2450 over UART).
- `python_dsp/` is the processing side: `dsp_filters.py` (Hampel, Butterworth band-pass, peak detector, STFT), `activity_classifier.py`, `mesh_trilateration.py` (least-squares position from several nodes), `csi_physics_lab.py` (live Matplotlib view) and `dataset_recorder.py` (CSV capture).
- The HTML files are browser front ends that read the board over the Web Serial API in Chrome or Edge: `radar_3d_hologram.html` (three.js, vendored as `three.min.js` and `OrbitControls.js`), `radar_map.html` and `radar_spatial_tracker.html`.
- `library_radar.py`, `radar_monitor.py` and `radar_terminal_2d.py`, with their `.ps1` twins, are terminal monitors for the serial stream.
- `docs/` has the derivations the filters are based on, the multi-node geometry, and the wiring notes.

## Setup
Flash a sketch from `firmware/` with the Arduino IDE (ESP32 core, board ESP32-S3 Dev Module). Edit the `ssid` and `password` placeholders in `esp32s3_csi_node.ino` before flashing; they are not read from the environment. The serial port is hardcoded as `COM11` in the Python monitors and the CSV recorder takes `--port`; change it to the port Windows assigns.

```
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python python_dsp\csi_physics_lab.py
```

The `.bat` files start the same things with a double click. The browser front ends open as plain files; no server is needed.

## Environment variables
| Var | Purpose | Where to get it |
| --- | ------- | --------------- |
| none | Wi-Fi credentials live only in the firmware source placeholders; never commit real values | your router |

## Tests
```
python -m unittest discover -s tests
```
Ten tests cover the filters, the classifier thresholds, trilateration convergence and the false-positive cases (empty room, a single beacon spike, typing versus walking). They need numpy and scipy only.
