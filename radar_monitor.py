import sys
import time
import re
import serial

PORT = "COM11"
BAUD = 115200

def main():
    print("=" * 65, flush=True)
    print("   ESP32-S3 WI-FI CSI RADAR - LIVE PHYSICAL PRESENCE MONITOR   ", flush=True)
    print("=" * 65, flush=True)
    print(f"Opening {PORT} at {BAUD} baud...", flush=True)

    try:
        ser = serial.Serial(PORT, BAUD, timeout=1)
        ser.dtr = True
        ser.rts = False
    except Exception as e:
        print(f"[!] Could not open {PORT}: {e}", flush=True)
        print("Tip: Make sure the Serial Monitor in Arduino IDE is closed so it doesn't hold the port!", flush=True)
        return

    print("[+] Port opened. Waiting for ESP32 connection & Wi-Fi handshake...", flush=True)

    pattern = re.compile(r"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)")
    baseline_samples = []
    baseline = 0.80
    sample_count = 0
    last_status = ""

    # Clear initial buffer
    ser.reset_input_buffer()

    while True:
        try:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            match = pattern.search(line)
            if not match:
                if "Wi-Fi Connected" in line or "IP:" in line or "Engine: ACTIVE" in line:
                    print(f"    {line}", flush=True)
                continue

            metric = float(match.group(1))
            rssi = int(match.group(2))
            csi_len = int(match.group(3))
            packets = int(match.group(4))

            # Calibration phase: first 20 valid packets
            if len(baseline_samples) < 20:
                baseline_samples.append(metric)
                pct = int(len(baseline_samples) * 5)
                print(f"[Calibrating ambient baseline: {pct}%] Please stand still...", flush=True)
                if len(baseline_samples) == 20:
                    baseline = sum(baseline_samples) / len(baseline_samples)
                    print(f"\n[+] Baseline Established: {baseline:.2f} (Monitoring active!)\n", flush=True)
                    print("-" * 65, flush=True)
                continue

            diff = metric - baseline
            ratio = metric / (baseline if baseline > 0.05 else 0.5)

            # Classify physical wave disturbance
            if ratio > 1.40 or diff > 0.35:
                status = "🚨 MOTION DETECTED (Walking / moving)"
            elif ratio > 1.15 or diff > 0.15:
                status = "🟡 PRESENCE (Sitting still / breathing)"
            else:
                status = "🟢 STILL (Room empty or quiet)"

            sample_count += 1

            # Build ASCII bar visualization
            bar_len = min(25, max(1, int(ratio * 10)))
            bar = "█" * bar_len + "░" * (25 - bar_len)
            ts = time.strftime("%H:%M:%S")

            if status != last_status or sample_count % 8 == 0:
                print(f"[{ts}] {status:<42} | Disturbance: [{bar}] ({metric:.2f})", flush=True)
                last_status = status

        except KeyboardInterrupt:
            print("\n\n[+] Stopped monitoring.", flush=True)
            break
        except Exception as e:
            time.sleep(0.1)

    ser.close()

if __name__ == "__main__":
    main()
