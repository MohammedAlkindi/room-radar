# room-radar

## Stack
Arduino C++ firmware for ESP32-S3 (Wi-Fi CSI and HLK-LD2450 mmWave), Python 3.14 DSP with numpy, scipy and matplotlib, and static HTML front ends using the Web Serial API and three.js.

## Commands
- Install: `py -m venv .venv; .\.venv\Scripts\Activate.ps1; pip install -r requirements.txt`
- Test: `python -m unittest discover -s tests`
- Flash: Arduino IDE, board ESP32-S3 Dev Module, one sketch per folder under `firmware/`

## Rules
- No hardcoded secrets or API keys anywhere. The Wi-Fi `ssid` and `password` in `firmware/esp32s3_csi_node/esp32s3_csi_node.ino` stay as placeholders in git.
- Serial and hardware I/O stay in the monitors, the recorder and `csi_physics_lab.py`; the filters, classifier and trilaterator in `python_dsp/` take arrays and return values so they can be unit tested.
- Normalize errors before they reach the client.
- One logical change per commit; never commit with tests failing.
- venv always; `requirements.txt` pinned; deterministic logic separated from I/O.
- Do not restate the claims in `docs/` as results. The Wi-Fi CSI track was never accurate in practice (see README Status); a new accuracy claim needs a recorded dataset and a number produced in this repo.
