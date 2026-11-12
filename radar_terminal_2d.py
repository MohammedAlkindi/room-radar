import sys
import time
import re
import random
import serial

PORT = "COM11"
BAUD = 115200

# ANSI color codes
RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
GRAY = "\033[90m"
HOME = "\033[H"
CLEAR = "\033[2J"

GRID_W = 68
GRID_H = 15

# Room positions
person_x = 50.0
person_y = 11.0
target_x = 50.0
target_y = 11.0

def build_grid(status, metric, baseline, rssi, packets):
    global person_x, person_y, target_x, target_y

    # Move target if in motion
    if status == "MOTION":
        if abs(person_x - target_x) < 2 and abs(person_y - target_y) < 2:
            dest = random.choice([(10, 3), (52, 3), (34, 7), (12, 11), (50, 11)])
            target_x, target_y = dest
        person_x += (target_x - person_x) * 0.35
        person_y += (target_y - person_y) * 0.35
    elif status == "PRESENCE":
        target_x, target_y = 50.0, 11.0
        person_x += (target_x - person_x) * 0.20
        person_y += (target_y - person_y) * 0.20

    px = int(round(person_x))
    py = int(round(person_y))

    lines = []
    lines.append(f"{CYAN}+" + ("-" * (GRID_W - 2)) + f"+{RESET}")
    lines.append(f"{CYAN}|{BOLD}                 ESP32-S3 2D WI-FI CSI RADAR CONSOLE                {RESET}{CYAN}|{RESET}")
    lines.append(f"{CYAN}+" + ("-" * (GRID_W - 2)) + f"+{RESET}")

    for y in range(GRID_H):
        row = []
        for x in range(GRID_W):
            if x == 0 or x == GRID_W - 1:
                row.append(f"{CYAN}|{RESET}")
                continue

            # Bed (Top Left: x 3..18, y 1..4)
            if 3 <= x <= 18 and 1 <= y <= 4:
                if y == 2 and 6 <= x <= 15:
                    label = "[BED:ZONE]"
                    row.append(f"{CYAN}{label[x-6]}{RESET}")
                elif x == 3 or x == 18 or y == 1 or y == 4:
                    row.append(f"{GRAY}#{RESET}")
                else:
                    row.append(f"{GRAY}.{RESET}")
                continue

            # Wardrobe / Closet (Top Right: x 46..62, y 1..4)
            if 46 <= x <= 62 and 1 <= y <= 4:
                if y == 2 and 49 <= x <= 58:
                    label = "[WARDROBE]"
                    row.append(f"{CYAN}{label[x-49]}{RESET}")
                elif x == 46 or x == 62 or y == 1 or y == 4:
                    row.append(f"{GRAY}#{RESET}")
                else:
                    row.append(f"{GRAY}.{RESET}")
                continue

            # Work Desk & ESP32 (Bottom Right: x 44..62, y 9..13)
            if 44 <= x <= 62 and 9 <= y <= 13:
                if y == 10 and 48 <= x <= 58:
                    label = "[DESK:WORK]"
                    row.append(f"{GREEN}{label[x-48]}{RESET}")
                elif y == 12 and 48 <= x <= 58:
                    label = "(ESP32:RX)"
                    row.append(f"{GREEN}{label[x-48]}{RESET}")
                elif x == 44 or x == 62 or y == 9 or y == 13:
                    row.append(f"{GRAY}#{RESET}")
                else:
                    row.append(f"{GRAY}.{RESET}")
                continue

            # Bookshelf (Bottom Left: x 3..18, y 9..13)
            if 3 <= x <= 18 and 9 <= y <= 13:
                if y == 11 and 6 <= x <= 15:
                    label = "[BOOKSHELF]"
                    row.append(f"{CYAN}{label[x-6]}{RESET}")
                elif x == 3 or x == 18 or y == 9 or y == 13:
                    row.append(f"{GRAY}#{RESET}")
                else:
                    row.append(f"{GRAY}.{RESET}")
                continue

            # Phone Hotspot Node (x 10..17, y 6)
            if 10 <= x <= 17 and y == 6:
                label = "T(PHONE)"
                row.append(f"{CYAN}{label[x-10]}{RESET}")
                continue

            # Doorway (Bottom Center: x 28..37, y 14)
            if y == 14 and 28 <= x <= 37:
                label = "[ENTRY:DOOR]"
                row.append(f"{GRAY}{label[x-28]}{RESET}")
                continue

            # Human Target Marker
            if x == px and y == py:
                if status == "MOTION":
                    row.append(f"{RED}{BOLD}W{RESET}")
                elif status == "PRESENCE":
                    row.append(f"{YELLOW}{BOLD}P{RESET}")
                else:
                    row.append(" ")
                continue
            if (x == px - 1 or x == px + 1) and y == py and status == "MOTION":
                row.append(f"{RED}*{RESET}")
                continue

            # Radio Multipath Ray between Phone (10, 6) and ESP32 (50, 11)
            slope = (11 - 6) / (50 - 10)
            exp_y = int(round(6 + (x - 10) * slope))
            if 18 < x < 44 and y == exp_y:
                if status == "MOTION":
                    row.append(f"{RED}~{RESET}")
                elif status == "PRESENCE":
                    row.append(f"{YELLOW}-{RESET}")
                else:
                    row.append(f"{GRAY}.{RESET}")
                continue

            row.append(" ")

        lines.append("".join(row))

    lines.append(f"{CYAN}+" + ("-" * (GRID_W - 2)) + f"+{RESET}")

    bar_max = 26
    filled = max(1, min(bar_max, int(metric * 6.5)))
    bar = "=" * filled + "-" * (bar_max - filled)

    if status == "MOTION":
        status_banner = f"{RED}{BOLD}[ALERT] MOTION DETECTED (Walking / Moving in Room){RESET}"
    elif status == "PRESENCE":
        status_banner = f"{YELLOW}{BOLD}[SENSE] HUMAN PRESENCE (Breathing / Subtle Motion){RESET}"
    else:
        status_banner = f"{GREEN}[QUIET] ROOM EMPTY / STILL                         {RESET}"

    lines.append(f"  STATUS: {status_banner}")
    lines.append(f"  RF DISTURBANCE: [{bar}] {BOLD}{metric:.2f}{RESET} (Baseline: {baseline:.2f})")
    lines.append(f"  WI-FI RSSI: {rssi} dBm  |  CSI PACKETS: {packets}  |  TARGET: (X: {px}, Y: {py})")
    lines.append(f"{GRAY}  Press [Ctrl + C] to exit | Run 'launch_radar_map.bat' for HD Web{RESET}")

    return "\n".join(lines)

def main():
    print(f"\n{CYAN}=================================================================={RESET}", flush=True)
    print(f"{CYAN}   ESP32-S3 2D WI-FI RADAR - LIVE PHYSICAL PRESENCE CONSOLE       {RESET}", flush=True)
    print(f"{CYAN}=================================================================={RESET}", flush=True)
    print(f"Opening {PORT} at {BAUD} baud...", flush=True)

    try:
        ser = serial.Serial(port=PORT, baudrate=BAUD, timeout=1.0)
        ser.dtr = True
        ser.rts = False
    except Exception as e:
        print(f"{RED}[!] Error opening {PORT}: {e}{RESET}", flush=True)
        print("Tip: If another terminal or Serial Monitor is using COM11, close it first!", flush=True)
        sys.exit(1)

    print(f"{GREEN}[+] Connected! Calibrating ambient baseline (please stand still)...{RESET}", flush=True)

    baseline_samples = []
    baseline = 1.20
    pattern = re.compile(r"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)")

    ser.reset_input_buffer()

    while len(baseline_samples) < 20:
        line = ser.readline().decode("utf-8", errors="ignore").strip()
        m = pattern.search(line)
        if m:
            baseline_samples.append(float(m.group(1)))
            pct = int(len(baseline_samples) * 5)
            sys.stdout.write(f"\r[Calibrating Baseline: {pct}%] Please stand still...")
            sys.stdout.flush()

    baseline = sum(baseline_samples) / len(baseline_samples)
    print(f"\n{GREEN}[+] Baseline Established: {baseline:.2f}! Launching 2D Console Map...{RESET}\n", flush=True)
    time.sleep(0.5)

    print(CLEAR + HOME, end="", flush=True)

    try:
        while True:
            line = ser.readline().decode("utf-8", errors="ignore").strip()
            if not line:
                continue

            m = pattern.search(line)
            if not m:
                continue

            metric = float(m.group(1))
            rssi = int(m.group(2))
            packets = int(m.group(4))

            if metric >= 1.65:
                status = "MOTION"
            elif metric >= 1.28:
                status = "PRESENCE"
            else:
                status = "STILL"

            frame = build_grid(status, metric, baseline, rssi, packets)
            sys.stdout.write(HOME + frame)
            sys.stdout.flush()

    except KeyboardInterrupt:
        print("\n\n[+] Exited radar console. Bye!", flush=True)
    finally:
        ser.close()

if __name__ == "__main__":
    main()
