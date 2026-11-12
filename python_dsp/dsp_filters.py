"""
Digital Signal Processing (DSP) Core for Wi-Fi CSI Radar
========================================================
Implements real-time filtering, physiological vital sign extraction,
Hampel outlier removal, and spectral analysis for commodity RF sensing.

Part of the ESP32-S3 Wi-Fi CSI Spatial Radar Project.
"""

from collections import deque
import numpy as np
from scipy import signal

class HampelFilter:
    """
    Hampel filter for outlier detection and replacement using
    Median Absolute Deviation (MAD), with zero-variance protection.
    """
    def __init__(self, window_size=7, n_sigmas=3.0, min_threshold=0.15):
        self.window_size = window_size
        self.n_sigmas = n_sigmas
        self.min_threshold = min_threshold
        self.k = 1.4826  # Scale factor for Gaussian distribution

    def filter(self, x):
        n = len(x)
        y = np.copy(x)
        k_w = self.window_size // 2

        for i in range(k_w, n - k_w):
            window = x[i - k_w : i + k_w + 1]
            med = np.median(window)
            mad = self.k * np.median(np.abs(window - med))
            # Fall back to min_threshold if background is completely flat (MAD == 0)
            threshold = max(self.n_sigmas * mad, self.min_threshold)

            if np.abs(x[i] - med) > threshold:
                y[i] = med
        return y


class VitalSignFilter:
    """
    Dual-stage digital bandpass filter for isolating human biometrics:
      - Respiration: 0.12 - 0.45 Hz (7.2 - 27.0 Breaths/Min)
      - Ballistocardiography (Cardiac Pulse): 0.8 - 2.0 Hz (48 - 120 BPM)
    """
    def __init__(self, fs=12.5):
        self.fs = fs
        nyq = 0.5 * fs

        # 4th-order Butterworth for Respiration
        self.b_resp, self.a_resp = signal.butter(
            4, [0.12 / nyq, 0.45 / nyq], btype='bandpass'
        )

        # 3rd-order Butterworth for Cardiac Pulse
        self.b_cardiac, self.a_cardiac = signal.butter(
            3, [0.80 / nyq, 2.00 / nyq], btype='bandpass'
        )

    def extract_respiration(self, raw_signal):
        """Detrend and bandpass filter chest breathing."""
        if len(raw_signal) < 18:
            return np.zeros_like(raw_signal)
        detrended = raw_signal - np.mean(raw_signal)
        try:
            return signal.filtfilt(self.b_resp, self.a_resp, detrended)
        except Exception:
            return detrended

    def extract_cardiac(self, raw_signal):
        """Detrend and bandpass filter micro-pulse ballistocardiography."""
        if len(raw_signal) < 18:
            return np.zeros_like(raw_signal)
        detrended = raw_signal - np.mean(raw_signal)
        try:
            return signal.filtfilt(self.b_cardiac, self.a_cardiac, detrended)
        except Exception:
            return detrended


class PhysiologicalPeakDetector:
    """
    Adaptive peak detector with refractory suppression and rate estimation.
    """
    def __init__(self, fs=12.5, min_interval_seconds=1.8, max_interval_seconds=6.0):
        self.fs = fs
        self.min_dist_samples = int(fs * min_interval_seconds)
        self.max_dist_samples = int(fs * max_interval_seconds)
        self.recent_bpm = None
        self.confidence = 0.0

    def analyze(self, filtered_signal):
        """
        Find peaks, calculate instantaneous BPM, and output confidence score.
        Returns: (bpm, confidence, peak_indices)
        """
        if len(filtered_signal) < self.min_dist_samples * 2:
            return (self.recent_bpm or 16.0), 0.0, []

        prominence = max(0.015, float(np.std(filtered_signal) * 0.35))
        peaks, _ = signal.find_peaks(
            filtered_signal,
            distance=self.min_dist_samples,
            prominence=prominence
        )

        if len(peaks) >= 2:
            intervals = np.diff(peaks) / self.fs
            valid_intervals = intervals[(intervals >= 1.5) & (intervals <= 7.0)]

            if len(valid_intervals) >= 1:
                avg_interval = np.median(valid_intervals)
                inst_bpm = 60.0 / avg_interval

                if self.recent_bpm is None:
                    self.recent_bpm = inst_bpm
                else:
                    self.recent_bpm = (self.recent_bpm * 0.65) + (inst_bpm * 0.35)

                var_interval = np.var(valid_intervals) if len(valid_intervals) > 1 else 0.0
                self.confidence = max(0.2, min(1.0, 1.0 - (var_interval * 2.0)))
            else:
                self.confidence = max(0.0, self.confidence - 0.05)
        else:
            self.confidence = max(0.0, self.confidence - 0.05)

        return (self.recent_bpm or 16.0), self.confidence, peaks


class STFTWaterfall:
    """
    Sliding-window Short-Time Fourier Transform (STFT) for micro-Doppler waterfall.
    """
    def __init__(self, fs=12.5, window_len=32, n_fft=64):
        self.fs = fs
        self.window_len = window_len
        self.n_fft = n_fft
        self.window = np.hanning(window_len)

    def compute_slice(self, raw_buffer):
        """Compute the latest FFT slice for the spectrogram."""
        if len(raw_buffer) < self.window_len:
            return np.zeros(self.n_fft // 2)

        data = np.array(list(raw_buffer)[-self.window_len:])
        data = (data - np.mean(data)) * self.window
        fft_res = np.abs(np.fft.rfft(data, n=self.n_fft))
        return fft_res[: self.n_fft // 2]
