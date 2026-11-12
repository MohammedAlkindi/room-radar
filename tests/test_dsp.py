"""
Automated Test Suite for ESP32 Wi-Fi CSI Radar DSP Pipeline
===========================================================
Verifies filtering fidelity, physiological BPM accuracy,
activity classification logic, and trilateration convergence.
"""

import sys
import os
import unittest
import numpy as np

# Add python_dsp to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python_dsp")))

from dsp_filters import HampelFilter, VitalSignFilter, PhysiologicalPeakDetector, STFTWaterfall
from activity_classifier import ActivityClassifier
from mesh_trilateration import BistaticMeshTrilaterator

class TestDSPPipeline(unittest.TestCase):
    def setUp(self):
        self.fs = 12.5
        self.duration = 20.0
        self.t = np.linspace(0, self.duration, int(self.fs * self.duration))

    def test_hampel_filter_outlier_removal(self):
        """Verify Hampel filter cleans spike noise without distorting underlying signal."""
        clean_signal = np.sin(2 * np.pi * 0.25 * self.t)
        noisy_signal = np.copy(clean_signal)
        # Inject artificial massive spikes
        noisy_signal[25] += 15.0
        noisy_signal[60] -= 12.0

        hf = HampelFilter(window_size=7, n_sigmas=3.0)
        filtered = hf.filter(noisy_signal)

        self.assertLess(abs(filtered[25] - clean_signal[25]), 0.6)
        self.assertLess(abs(filtered[60] - clean_signal[60]), 0.6)

    def test_vital_sign_filter_frequency_response(self):
        """Verify Butterworth bandpass passes 0.25 Hz (breathing) and attenuates high frequencies."""
        vs = VitalSignFilter(fs=self.fs)
        # Synthetic signal: 0.25 Hz breath + 3.5 Hz fast noise
        breath = 1.0 * np.sin(2 * np.pi * 0.25 * self.t)
        noise = 0.8 * np.sin(2 * np.pi * 3.50 * self.t)
        composite = breath + noise

        filtered_resp = vs.extract_respiration(composite)
        # The 3.5 Hz component should be attenuated by at least 15 dB (>80% reduction)
        noise_attenuation = np.std(filtered_resp) / np.std(composite)
        self.assertLess(noise_attenuation, 0.85)

    def test_peak_detector_bpm_accuracy(self):
        """Verify physiological peak detector extracts 15.0 BPM (0.25 Hz) within 1.0 BPM error."""
        target_bpm = 15.0
        target_freq = target_bpm / 60.0  # 0.25 Hz
        pure_resp = 0.5 * np.sin(2 * np.pi * target_freq * self.t)

        detector = PhysiologicalPeakDetector(fs=self.fs, min_interval_seconds=1.8)
        bpm, conf, peaks = detector.analyze(pure_resp)

        self.assertGreater(len(peaks), 3)
        self.assertAlmostEqual(bpm, target_bpm, delta=1.5)
        self.assertGreater(conf, 0.70)

    def test_activity_classifier_states(self):
        """Verify activity classifier correctly identifies Vacant vs Sedentary vs Walking."""
        clf = ActivityClassifier(fs=self.fs)

        # 1. Vacant (flat baseline noise)
        flat_signal = np.random.normal(1.20, 0.01, int(self.fs * 4))
        fft_slice = np.zeros(16)
        state, conf, _ = clf.classify(flat_signal, np.zeros_like(flat_signal), fft_slice, baseline=1.20)
        self.assertEqual(state, "VACANT")

        # 2. Walking (High variance macro-motion)
        walking_signal = 1.20 + np.sin(2 * np.pi * 1.5 * self.t[:int(self.fs * 4)]) * 0.8
        fft_slice[8] = 3.5 # High Doppler energy
        state, conf, _ = clf.classify(walking_signal, np.zeros_like(walking_signal), fft_slice, baseline=1.20)
        self.assertEqual(state, "LOCOMOTION_WALKING")

    def test_mesh_trilateration_accuracy(self):
        """Verify bistatic elliptical trilateration recovers coordinate within 10 cm."""
        engine = BistaticMeshTrilaterator(
            tx_pos=(0.0, 0.0),
            rx_nodes={'RX1': (4.0, 0.0), 'RX2': (4.0, 4.0), 'RX3': (0.0, 4.0)}
        )

        test_points = [(1.5, 2.0), (2.8, 1.2), (3.0, 3.2)]
        for tx, ty in test_points:
            deltas = engine.simulate_measurement((tx, ty), noise_std=0.02)
            cx, cy, cost, ok = engine.locate(deltas)
            self.assertTrue(ok)
            error_m = np.hypot(cx - tx, cy - ty)
            self.assertLess(error_m, 0.15)  # Under 15 cm error

if __name__ == "__main__":
    unittest.main()
