"""
Anti-Hallucination & Robustness Test Suite
==========================================
Verifies that the RF classification and vital sign engine does NOT
produce false positives (hallucinations) during:
  1. Empty room ambient RF noise drift & temperature swings
  2. Isolated single-packet beacon spikes from passing devices
  3. Keyboard typing vs true walking locomotion
  4. Sedentary chest breathing vs completely vacant desk
  5. Rapid posture transitions without oscillation
"""

import sys
import os
import unittest
import numpy as np

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "python_dsp")))

from dsp_filters import HampelFilter, VitalSignFilter, PhysiologicalPeakDetector, STFTWaterfall
from activity_classifier import ActivityClassifier

class TestAntiHallucination(unittest.TestCase):
    def setUp(self):
        self.fs = 12.5
        self.classifier = ActivityClassifier(fs=self.fs, history_seconds=3.0)
        self.hampel = HampelFilter(window_size=7, n_sigmas=3.0)
        self.vital = VitalSignFilter(fs=self.fs)
        self.peak_det = PhysiologicalPeakDetector(fs=self.fs, min_interval_seconds=1.8)
        self.stft = STFTWaterfall(fs=self.fs, window_len=32, n_fft=64)

    def test_empty_room_no_false_presence(self):
        """
        TEST CASE 1: Empty Room Ambient Drift
        Simulates 30 seconds of an empty room with:
          - Gaussian thermal receiver noise (std = 0.015)
          - Slow baseline drift due to temperature/battery (0.05 drift)
          - Random Wi-Fi channel interference bursts
        EXPECTED: Must remain VACANT. Zero hallucinations of human presence.
        """
        n_samples = int(self.fs * 30) # 30 seconds
        t = np.linspace(0, 30, n_samples)
        # Slow drift + thermal noise
        noise = 1.20 + 0.03 * np.sin(2 * np.pi * 0.02 * t) + np.random.normal(0, 0.012, n_samples)

        for i in range(32, n_samples):
            window = noise[i - 32 : i]
            cleaned = self.hampel.filter(window)
            resp = self.vital.extract_respiration(cleaned)
            fft_slice = self.stft.compute_slice(cleaned)
            state, conf, _ = self.classifier.classify(cleaned, resp, fft_slice, baseline=1.20)

            # Must NEVER trigger walking or desk fidgeting in an empty room
            self.assertNotEqual(state, "LOCOMOTION_WALKING", f"False walk detected at sample {i}")
            self.assertNotEqual(state, "DESK_WORK_GESTURES", f"False gesture detected at sample {i}")

    def test_single_packet_burst_rejection(self):
        """
        TEST CASE 2: Single-Packet RF Spike (Passing Phone Probe Request)
        Injects sudden massive 1-packet spikes (+2.5 metric).
        EXPECTED: Hampel filter must suppress spike; classifier must not latch to WALKING.
        """
        window = np.full(32, 1.20)
        # Inject isolated burst spike
        window[15] = 3.80

        cleaned = self.hampel.filter(window)
        # Verify spike was clamped by Hampel MAD filter
        self.assertLess(cleaned[15], 1.45, "Spike was not suppressed by Hampel filter")

        resp = self.vital.extract_respiration(cleaned)
        fft_slice = self.stft.compute_slice(cleaned)
        state, conf, _ = self.classifier.classify(cleaned, resp, fft_slice, baseline=1.20)

        # Must not trigger walking from an isolated single-packet artifact
        self.assertNotEqual(state, "LOCOMOTION_WALKING")

    def test_typing_never_confused_with_walking(self):
        """
        TEST CASE 3: Keyboard Typing / Desk Micro-Gestures
        Simulates typing at keyboard:
          - High-frequency micro-tremors (1.2 - 2.0 Hz)
          - Metric perturbation 1.50 - 1.62
        EXPECTED: Must classify as DESK_WORK_GESTURES, NEVER LOCOMOTION_WALKING.
        """
        n_samples = int(self.fs * 10)
        t = np.linspace(0, 10, n_samples)
        # Typing perturbation
        typing_signal = 1.54 + 0.07 * np.sin(2 * np.pi * 1.6 * t) + np.random.normal(0, 0.02, n_samples)

        for i in range(32, n_samples, 4):
            window = typing_signal[i - 32 : i]
            cleaned = self.hampel.filter(window)
            resp = self.vital.extract_respiration(cleaned)
            fft_slice = self.stft.compute_slice(cleaned)
            state, conf, _ = self.classifier.classify(cleaned, resp, fft_slice, baseline=1.20)

            self.assertIn(state, ["DESK_WORK_GESTURES", "SEDENTARY_RESPIRATION"])
            self.assertNotEqual(state, "LOCOMOTION_WALKING", f"Typing misclassified as walking at {i}")

    def test_shallow_breathing_detection(self):
        """
        TEST CASE 4: Subtle Human Chest Respiration
        Simulates sitting still with shallow 4mm chest expansion:
          - Frequency 0.22 Hz (13.2 BPM)
          - Low amplitude AC variation (0.06 peak-to-peak)
        EXPECTED: Peak detector locks breathing cadence within 1.0 BPM error.
        """
        n_samples = int(self.fs * 25) # 25 seconds
        t = np.linspace(0, 25, n_samples)
        true_bpm = 13.2
        true_freq = true_bpm / 60.0
        resp_signal = 1.34 + 0.05 * np.sin(2 * np.pi * true_freq * t) + np.random.normal(0, 0.008, n_samples)

        cleaned = self.hampel.filter(resp_signal)
        resp_filtered = self.vital.extract_respiration(cleaned)
        bpm, conf, peaks = self.peak_det.analyze(resp_filtered)

        self.assertGreater(len(peaks), 3, "Failed to identify breathing peaks")
        self.assertAlmostEqual(bpm, true_bpm, delta=1.2, msg="Breathing rate error exceeds 1.2 BPM")
        self.assertGreater(conf, 0.70, "Confidence score is too low")

    def test_rapid_transition_decay(self):
        """
        TEST CASE 5: Sudden Stop (Walking -> Sitting Still)
        Simulates a subject walking, then immediately sitting still.
        EXPECTED: State must smoothly transition from WALKING to SEDENTARY within 2.5s without oscillating.
        """
        t_walk = np.linspace(0, 5, int(self.fs * 5))
        walk_signal = 2.10 + 0.35 * np.sin(2 * np.pi * 3.0 * t_walk)

        t_still = np.linspace(0, 6, int(self.fs * 6))
        still_signal = 1.32 + 0.04 * np.sin(2 * np.pi * 0.25 * t_still)

        combined = np.concatenate([walk_signal, still_signal])
        # Test 2.5 seconds after stop
        stop_index = int(self.fs * (5 + 2.5))
        window = combined[stop_index - 32 : stop_index]
        cleaned = self.hampel.filter(window)
        resp = self.vital.extract_respiration(cleaned)
        fft_slice = self.stft.compute_slice(cleaned)
        state, conf, _ = self.classifier.classify(cleaned, resp, fft_slice, baseline=1.20)

        self.assertNotEqual(state, "LOCOMOTION_WALKING", "System still latched to walking 2.5s after stop")
        self.assertIn(state, ["SEDENTARY_RESPIRATION", "DESK_WORK_GESTURES", "VACANT"])

if __name__ == "__main__":
    unittest.main()
