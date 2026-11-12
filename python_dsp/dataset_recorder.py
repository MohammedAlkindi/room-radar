"""
Wi-Fi CSI Session Dataset Recorder
==================================
Logs synchronized physical-layer CSI telemetry to timestamped CSV files
for scientific model training, baseline calibration, and benchmark verification.

Part of the ESP32-S3 Wi-Fi CSI Spatial Radar Project.
"""

import sys
import os
import time
import re
import argparse
from datetime import datetime
import serial

PATTERN = re.compile(r"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)")

def record_session(port="COM11", baud=115200, label="unlabeled", duration=60, output_dir="data"):
    os.makedirs(output_dir, exist_ok=True)
    timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = os.path.join(output_dir, f"csi_session_{label}_{timestamp_str}.csv")

    print("==================================================================")
    print("           ESP32-S3 Wi-Fi CSI Dataset Ingestion Engine            ")
    print("==================================================================")
    print(f"Port:       {port}")
    print(f"Baud:       {baud}")
    print(f"Label:      {label}")
    print(f"Duration:   {duration} seconds")
    print(f"Output:     {filename}")
    print("------------------------------------------------------------------")

    try:
        ser = serial.Serial(port, baud, timeout=1.0)
        ser.dtr = True
        ser.rts = False
        print(f"[+] Connected to {port}! Recording begins now...")
    except Exception as e:
        print(f"[!] Error: Unable to open {port}: {e}")
        print("[!] Ensure Chrome Web Serial and other serial monitors are closed.")
        sys.exit(1)

    start_time = time.time()
    packet_logged = 0

    with open(filename, "w", encoding="utf-8") as f:
        f.write("unix_timestamp,elapsed_sec,metric,rssi,csi_len,packet_num,label\n")

        try:
            while True:
                now = time.time()
                elapsed = now - start_time
                if duration > 0 and elapsed >= duration:
                    break

                line = ser.readline().decode("utf-8", errors="ignore").strip()
                if not line:
                    continue

                m = PATTERN.search(line)
                if m:
                    metric = float(m.group(1))
                    rssi = int(m.group(2))
                    csi_len = int(m.group(3))
                    pkts = int(m.group(4))

                    f.write(f"{now:.4f},{elapsed:.3f},{metric:.2f},{rssi},{csi_len},{pkts},{label}\n")
                    f.flush()
                    packet_logged += 1

                    if packet_logged % 15 == 0:
                        pct = int((elapsed / duration) * 100) if duration > 0 else 0
                        sys.stdout.write(f"\r[{pct}%] Recorded: {packet_logged} packets | Metric: {metric:.2f} | RSSI: {rssi} dBm")
                        sys.stdout.flush()

        except KeyboardInterrupt:
            print("\n[!] Recording interrupted by user.")

    print(f"\n[+] Session complete! {packet_logged} packets written to {filename}")
    ser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Record ESP32-S3 Wi-Fi CSI Sessions to CSV.")
    parser.add_argument("--port", default="COM11", help="Serial COM port (default: COM11)")
    parser.add_argument("--baud", type=int, default=115200, help="Baud rate (default: 115200)")
    parser.add_argument("--label", default="sedentary_breathing", help="Activity label (e.g., vacant, sitting, typing, walking)")
    parser.add_argument("--duration", type=int, default=60, help="Duration in seconds (default: 60)")
    parser.add_argument("--outdir", default="data", help="Output directory")

    args = parser.parse_args()
    record_session(port=args.port, baud=args.baud, label=args.label, duration=args.duration, output_dir=args.outdir)
