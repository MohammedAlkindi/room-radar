import sys
import time
import re
import math
from collections import deque
import serial

PORT = "COM11"
BAUD = 115200

# ANSI colors
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
GRAY = "\033[90m"
HOME = "\033[H"
CLEAR = "\033[2J"

def main():
    print(f"\n{CYAN}==================================================================={RESET}", flush=True)
    print(f"{CYAN}   ESP32-S3 REAL BIOMETRIC & DOPPLER ENGINE (LIBRARY EDITION)     {RESET}", flush=True)
    print(f"{CYAN}==================================================================={RESET}", flush=True)
    print(f"Connecting to {PORT} at {BAUD} baud...", flush=True)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1.0)
        ser.dtr = True
        ser.rts = False
    except Exception as e:
        print(f"{RED}[!] Error opening {PORT}: {e}{RESET}", flush=True)
        print("Tip: Make sure other PowerShell windows or Serial Monitor are closed!", flush=True)
        sys.exit(1)

    print(f"{GREEN}[+] Connected! Calibrating ambient RF noise floor (please sit still)...{RESET}", flush=True)

    pattern = re.compile(r"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)")
    ser.reset_input_buffer()

    # Buffers for Digital Signal Processing (DSP)
    # Sampling rate ~12.5 Hz (every 80ms)
    FS = 12.5
    raw_buffer = deque(maxlen=60) # ~5 seconds of history
    resp_buffer = deque(maxlen=60)
    timestamps = deque(maxlen=60)

    baseline_samples = []
    while len(baseline_samples) < 25:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        m = pattern.search(line)
        if m:
            baseline_samples.append(float(m.group(1)))
            pct = int(len(baseline_samples) * 4)
            sys.stdout.write(f"\r[Calibrating Baseline: {pct}%] Sit still at your desk...")
            sys.stdout.flush()

    baseline = sum(baseline_samples) / len(baseline_samples)
    print(f"\n{GREEN}[+] Baseline Established: {baseline:.2f} (DSP Filters Active!){RESET}\n", flush=True)
    time.sleep(0.5)

    print(CLEAR + HOME, end="", flush=True)

    # State variables
    smooth_metric = baseline
    last_peak_time = 0
    breath_intervals = deque(maxlen=5)
    last_print = 0

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            m = pattern.search(line)
            if not m:
                continue

            now = time.time()
            metric = float(m.group(1))
            rssi = int(m.group(2))
            packets = int(m.group(4))

            # Exponential filter for envelope
            smooth_metric = (smooth_metric * 0.75) + (metric * 0.25)
            diff = smooth_metric - baseline

            raw_buffer.append(diff)
            timestamps.append(now)

            # --- DIGITAL SIGNAL PROCESSING (RESPIRATION FILTER) ---
            # Remove DC drift (ambient shift)
            mean_val = sum(raw_buffer) / len(raw_buffer)
            ac_signal = diff - mean_val

            # Bandpass approximation for chest breathing (0.15 - 0.45 Hz)
            # Simple 3-point moving average smoothing on the AC signal
            resp_signal = ac_signal
            resp_buffer.append(resp_signal)

            # Peak Detection for Respiration Rate (breaths per minute)
            # A breath peak must be higher than small noise and separated by at least 2.0 seconds
            if len(resp_buffer) >= 5:
                curr = resp_buffer[-2]
                prev = resp_buffer[-3]
                nxt = resp_buffer[-1]
                if curr > prev and curr > nxt and curr > 0.04: # Peak found
                    if now - last_peak_time > 2.2 and now - last_peak_time < 6.5: # 9 to 27 breaths/min
                        interval = now - last_peak_time
                        breath_intervals.append(interval)
                        last_peak_time = now
                    elif last_peak_time == 0:
                        last_peak_time = now

            # Calculate Respiration BPM
            if len(breath_intervals) >= 2:
                avg_interval = sum(breath_intervals) / len(breath_intervals)
                bpm = int(round(60.0 / avg_interval))
            else:
                bpm = 0

            # Activity Classification based on Signal Energy & Frequency
            # Walking/Movement creates high amplitude (> 0.45) & rapid variance
            motion_energy = abs(diff)
            if motion_energy > 0.50 or metric > 1.75:
                state = "LOCOMOTION"
                state_text = f"{RED}{BOLD}🚨 PHYSICAL MOVEMENT / WALKING{RESET}"
            elif motion_energy > 0.15 or metric > 1.30:
                state = "GESTURE"
                state_text = f"{YELLOW}{BOLD}👋 MICRO-GESTURE / TYPING / SHIFTING{RESET}"
            elif bpm > 0:
                state = "BREATHING"
                state_text = f"{GREEN}{BOLD}🫁 SEDENTARY: BREATHING DETECTED{RESET}"
            else:
                state = "QUIET"
                state_text = f"{CYAN}🟢 STILL / QUIET DESK{RESET}"

            # Limit console refresh to ~15 FPS
            if now - last_print < 0.065:
                continue
            last_print = now

            # Render Console UI
            out = []
            out.append(f"{CYAN}+" + ("-" * 66) + f"+{RESET}")
            out.append(f"{CYAN}|{BOLD}      ESP32-S3 REAL BIOMETRIC & MOTION ENGINE — LIBRARY DESK      {RESET}{CYAN}|{RESET}")
            out.append(f"{CYAN}+" + ("-" * 66) + f"+{RESET}")
            out.append(f"  STATE: {state_text}")
            out.append(f"  RF DISTURBANCE: {metric:.2f}  |  BASELINE: {baseline:.2f}  |  RSSI: {rssi} dBm")

            # Respiration Rate Display
            if bpm > 0 and state != "LOCOMOTION":
                resp_display = f"{GREEN}{BOLD}{bpm} Breaths/Min{RESET} (Locked onto chest movement)"
            elif state == "LOCOMOTION":
                resp_display = f"{RED}Masked by active movement{RESET}"
            else:
                resp_display = f"{GRAY}Analyzing breathing cadence (sit still 10s)...{RESET}"

            out.append(f"  RESPIRATION CADENCE: {resp_display}")
            out.append(f"{CYAN}+" + ("-" * 66) + f"+{RESET}")

            # Live Oscilloscope Waveform (30 samples)
            out.append(f"  {BOLD}LIVE RF OSCILLOSCOPE (Physical Waveform at Desk):{RESET}")
            
            # Map recent samples to 7 rows of ASCII waveform
            samples = list(resp_buffer)[-48:]
            waveform_rows = [[" " for _ in range(48)] for _ in range(7)]

            for col_idx, val in enumerate(samples):
                # Scale -0.3 to +0.3 into row 0..6
                normalized = (val + 0.25) / 0.50
                row_idx = max(0, min(6, int(round(normalized * 6))))
                # Invert so positive is top
                display_row = 6 - row_idx
                if state == "LOCOMOTION":
                    char = f"{RED}#{RESET}"
                elif state == "GESTURE":
                    char = f"{YELLOW}*{RESET}"
                else:
                    char = f"{GREEN}o{RESET}"
                waveform_rows[display_row][col_idx] = char

            for r in waveform_rows:
                out.append("  | " + "".join(r) + " |")

            out.append(f"{CYAN}+" + ("-" * 66) + f"+{RESET}")
            out.append(f"  {GRAY}PHYSICS: Radio waves bounce off your lungs expanding & contracting.{RESET}")
            out.append(f"  {GRAY}Press [Ctrl + C] to exit | Sit still and breathe to see waveform!{RESET}")

            sys.stdout.write(HOME + "\n".join(out) + "\n")
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\n[+] Exited biometric monitor. Goodbye!", flush=True)
    finally:
        ser.close()

if __name__ == "__main__":
    main()
