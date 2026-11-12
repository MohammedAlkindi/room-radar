"""
ESP32-S3 Wi-Fi CSI Scientific Physics Laboratory (Modular Edition)
==================================================================
Interactive multi-panel DSP dashboard using NumPy, SciPy, and Matplotlib.
Integrates VitalSignFilter, PhysiologicalPeakDetector, STFTWaterfall,
and ActivityClassifier.

Hardware: ESP32-S3 (COM11, 115200 baud)
"""

import sys
import os
import time
import re
from collections import deque
import serial
import numpy as np
from scipy import signal
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.animation import FuncAnimation

# Import modular DSP components
sys.path.insert(0, os.path.dirname(__file__))
from dsp_filters import VitalSignFilter, PhysiologicalPeakDetector, STFTWaterfall, HampelFilter
from activity_classifier import ActivityClassifier

# Serial Configuration
PORT = "COM11"
BAUD = 115200
FS = 12.5  # Sampling frequency (~80ms per packet)
WINDOW_SECONDS = 15
BUFFER_LEN = int(FS * WINDOW_SECONDS)

# State & Data Buffers
raw_metric_buffer = deque([1.20] * BUFFER_LEN, maxlen=BUFFER_LEN)
time_buffer = deque([0.0] * BUFFER_LEN, maxlen=BUFFER_LEN)
resp_filtered_buffer = deque([0.0] * BUFFER_LEN, maxlen=BUFFER_LEN)
spectrogram_history = deque([np.zeros(32)] * 60, maxlen=60)
detected_peaks_x = []
detected_peaks_y = []

current_bpm = 16.0
current_rssi = -41
current_metric = 1.20
ambient_baseline = 1.20
current_state = "STANDBY"
ser_conn = None

# Initialize DSP Modules
vital_filter = VitalSignFilter(fs=FS)
peak_detector = PhysiologicalPeakDetector(fs=FS, min_interval_seconds=1.8)
stft_engine = STFTWaterfall(fs=FS, window_len=32, n_fft=64)
classifier = ActivityClassifier(fs=FS, history_seconds=3.0)
hampel = HampelFilter(window_size=5, n_sigmas=3.0)

pattern = re.compile(r"RADAR:([0-9.]+),RSSI:([0-9-]+),CSI_LEN:([0-9]+),PACKETS:([0-9]+)")

def connect_serial():
    global ser_conn, PORT
    candidate_ports = [sys.argv[1]] if len(sys.argv) > 1 else ["COM11", "COM12", "COM13", "COM7"]
    for p in candidate_ports:
        try:
            ser_conn = serial.Serial(p, BAUD, timeout=0.05)
            ser_conn.dtr = True
            ser_conn.rts = False
            PORT = p
            print(f"[+] Successfully opened {PORT} at {BAUD} baud!")
            return True
        except Exception:
            continue
    print(f"[!] Warning: Could not open any serial port {candidate_ports}.")
    print("[!] Running in scientific SIMULATION mode.")
    return False

def read_serial_data():
    global current_metric, current_rssi, ser_conn
    if ser_conn and ser_conn.is_open:
        try:
            while ser_conn.in_waiting > 0:
                line = ser_conn.readline().decode('utf-8', errors='ignore').strip()
                m = pattern.search(line)
                if m:
                    current_metric = float(m.group(1))
                    current_rssi = int(m.group(2))
        except Exception:
            pass

def update_dsp():
    global current_bpm, current_state, detected_peaks_x, detected_peaks_y, ambient_baseline

    now = time.time()
    read_serial_data()

    raw_metric_buffer.append(current_metric)
    time_buffer.append(now)

    raw_arr = np.array(raw_metric_buffer)
    # Filter spikes with Hampel
    cleaned_raw = hampel.filter(raw_arr)

    # Respiration IIR Bandpass
    resp_filtered = vital_filter.extract_respiration(cleaned_raw)
    resp_filtered_buffer.clear()
    resp_filtered_buffer.extend(resp_filtered)

    # Physiological Peak Detection
    current_bpm, conf, peaks = peak_detector.analyze(resp_filtered)
    detected_peaks_x = peaks
    detected_peaks_y = resp_filtered[peaks] if len(peaks) > 0 else []

    # STFT Doppler Slice
    fft_slice = stft_engine.compute_slice(raw_metric_buffer)
    spectrogram_history.append(fft_slice)

    # Activity Classification
    current_state, state_conf, _ = classifier.classify(
        raw_metric_buffer, resp_filtered, fft_slice, baseline=ambient_baseline
    )

# Setup Matplotlib Dark Theme Dashboard
plt.style.use('dark_background')
fig = plt.figure(figsize=(11, 7), facecolor='#07080d')
fig.canvas.manager.set_window_title('ESP32-S3 Wi-Fi CSI Physics & Biometrics Lab')

gs = fig.add_gridspec(3, 2, hspace=0.38, wspace=0.22, left=0.07, right=0.96, top=0.91, bottom=0.08)

ax1 = fig.add_subplot(gs[0, :])  # Raw Perturbation
ax2 = fig.add_subplot(gs[1, 0])  # Respiration Filter
ax3 = fig.add_subplot(gs[1, 1])  # Power Spectral Density
ax4 = fig.add_subplot(gs[2, :])  # STFT Doppler Spectrogram Waterfall

for ax in [ax1, ax2, ax3, ax4]:
    ax.set_facecolor('#0f121a')
    ax.grid(True, color='#27272a', linestyle='--', linewidth=0.5, alpha=0.7)
    for spine in ax.spines.values():
        spine.set_color('#3f3f46')

ax1.set_title("1. RAW WI-FI CSI CHANNEL PERTURBATION (OFDM AMPLITUDE ENVELOPE)", fontsize=10, fontweight='bold', color='#38bdf8', loc='left')
ax1.set_ylabel("Perturbation", fontsize=8)
line_raw, = ax1.plot([], [], color='#38bdf8', linewidth=1.2, label='CSI Metric')
line_base, = ax1.plot([], [], color='#71717a', linestyle=':', linewidth=1.0, label='Ambient Baseline')
ax1.legend(loc='upper right', fontsize=8, facecolor='#18181b', edgecolor='#3f3f46')

ax2.set_title("2. DIGITAL BANDPASS: ISOLATED CHEST RESPIRATION (0.12 - 0.45 Hz)", fontsize=10, fontweight='bold', color='#34d399', loc='left')
ax2.set_ylabel("Displacement (a.u.)", fontsize=8)
line_resp, = ax2.plot([], [], color='#34d399', linewidth=1.4)
scatter_peaks = ax2.scatter([], [], color='#fb7185', s=30, zorder=5, label='Inhalation Peaks')

ax3.set_title("3. POWER SPECTRAL DENSITY (WELCH PSD)", fontsize=10, fontweight='bold', color='#fbbf24', loc='left')
ax3.set_xlabel("Frequency (Hz)", fontsize=8)
ax3.set_ylabel("Power", fontsize=8)
line_psd, = ax3.plot([], [], color='#fbbf24', linewidth=1.4)
ax3.set_xlim(0, 3.0)

ax4.set_title("4. DOPPLER-TIME SPECTROGRAM (MICRO-MOTION WATERFALL)", fontsize=10, fontweight='bold', color='#c084fc', loc='left')
ax4.set_xlabel("Time History (Slices)", fontsize=8)
ax4.set_ylabel("Doppler Freq (Hz)", fontsize=8)
im_spec = ax4.imshow(np.zeros((32, 60)), aspect='auto', origin='lower', cmap='plasma', extent=[0, 60, 0, FS / 2], vmin=0, vmax=2.5)

fig_title = fig.suptitle(
    f"ESP32-S3 CSI RADAR | {current_state} | RESPIRATION: {current_bpm:.1f} BPM | RSSI: {current_rssi} dBm",
    fontsize=11, fontweight='bold', color='#f4f4f5', y=0.97
)

def animate(frame):
    update_dsp()

    y_raw = list(raw_metric_buffer)
    x_t = np.linspace(-WINDOW_SECONDS, 0, len(y_raw))
    line_raw.set_data(x_t, y_raw)
    line_base.set_data(x_t, [ambient_baseline] * len(y_raw))
    ax1.set_xlim(-WINDOW_SECONDS, 0)
    ax1.set_ylim(min(y_raw) - 0.2, max(y_raw) + 0.3)

    y_resp = list(resp_filtered_buffer)
    line_resp.set_data(x_t, y_resp)
    if len(detected_peaks_x) > 0 and len(detected_peaks_y) > 0:
        px = x_t[detected_peaks_x]
        scatter_peaks.set_offsets(np.column_stack((px, detected_peaks_y)))
    else:
        scatter_peaks.set_offsets(np.empty((0, 2)))
    ax2.set_xlim(-WINDOW_SECONDS, 0)
    max_amp = max(0.15, np.max(np.abs(y_resp)) * 1.3)
    ax2.set_ylim(-max_amp, max_amp)

    ac_arr = np.array(raw_metric_buffer) - np.mean(raw_metric_buffer)
    freqs, psd = signal.welch(ac_arr, fs=FS, nperseg=min(len(ac_arr), 64))
    line_psd.set_data(freqs, psd)
    ax3.set_ylim(0, max(0.01, np.max(psd[:20]) * 1.2))

    spec_data = np.array(spectrogram_history).T
    im_spec.set_data(spec_data)

    state_color = '#34d399' if 'BREATHING' in current_state else ('#fbbf24' if 'VACANT' in current_state else '#fb7185')
    bpm_text = f"{current_bpm:.1f} BPM" if "WALKING" not in current_state else "MASKED BY MOVEMENT"
    fig_title.set_text(
        f"STATUS: {current_state}   |   RESPIRATION: {bpm_text}   |   SIGNAL: {current_rssi} dBm   |   METRIC: {current_metric:.2f}"
    )
    fig_title.set_color(state_color)

    return line_raw, line_resp, line_psd, im_spec

def main():
    print("=================================================================")
    print("      ESP32-S3 Wi-Fi CSI Scientific Physics Dashboard            ")
    print("=================================================================")
    connect_serial()
    ani = FuncAnimation(fig, animate, interval=80, blit=False, cache_frame_data=False)
    plt.show()

if __name__ == "__main__":
    main()
