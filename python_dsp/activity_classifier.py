"""
RF Activity & Kinematics Classifier
===================================
Classifies human spatial activity using statistical features,
spectral energy ratios, and heuristic threshold boundaries.

Classes:
  - VACANT: Empty room / background noise floor
  - SEDENTARY_RESPIRATION: Human sitting still, periodic breathing locked
  - DESK_WORK_GESTURES: Micro-gestures, keyboard typing, arm motion
  - LOCOMOTION_WALKING: Macro-displacement, walking across Fresnel zones
  - FALL_EVENT: Rapid acceleration/deceleration impact signature

Part of the ESP32-S3 Wi-Fi CSI Spatial Radar Project.
"""

from collections import deque
import numpy as np
from scipy import stats

class ActivityClassifier:
    def __init__(self, fs=12.5, min_samples=20, history_seconds=3.0):
        self.fs = fs
        self.min_samples = min_samples
        self.window_size = int(fs * history_seconds)
        self.current_state = "VACANT"
        self.state_confidence = 0.0
        self.fall_cooldown = 0

    def extract_features(self, raw_buffer, filtered_resp, fft_slice):
        """
        Extract physical & statistical features from recent CSI time-series:
          1. Variance (motion energy)
          2. Kurtosis (impulsiveness / sudden shocks)
          3. Respiration-to-Total energy ratio (RER)
          4. High-frequency Doppler energy ratio (HER)
        """
        if len(raw_buffer) < self.min_samples:
            return None

        recent_raw = np.array(list(raw_buffer))
        variance = float(np.var(recent_raw))
        mean_val = float(np.mean(recent_raw))
        kurt = float(stats.kurtosis(recent_raw)) if variance > 1e-6 else 0.0

        # Spectral energy distribution
        tot_power = float(np.sum(fft_slice)) + 1e-6
        # Respiration bins (0.15 - 0.45 Hz: bins 1 and 2 in 32-bin spectrum)
        resp_power = float(np.sum(fft_slice[1:3]))
        # High Doppler bins (> 2.0 Hz: bins 6+)
        high_power = float(np.sum(fft_slice[6:]))

        rer = resp_power / tot_power
        her = high_power / tot_power

        return {
            'variance': variance,
            'mean': mean_val,
            'kurtosis': kurt,
            'rer': rer,
            'her': her,
            'tot_power': tot_power
        }

    def classify(self, raw_buffer, filtered_resp, fft_slice, baseline=1.20):
        """
        Evaluate features and return (state_label, confidence_score, features_dict)
        """
        feats = self.extract_features(raw_buffer, filtered_resp, fft_slice)
        if feats is None:
            return self.current_state, 0.0, {}

        var = feats['variance']
        kurt = feats['kurtosis']
        mean = feats['mean']
        her = feats['her']
        rer = feats['rer']

        if self.fall_cooldown > 0:
            self.fall_cooldown -= 1

        # 1. Fall Event Detection
        if var > 0.35 and kurt > 4.5 and self.fall_cooldown == 0:
            self.current_state = "FALL_EVENT"
            self.state_confidence = 0.92
            self.fall_cooldown = int(self.fs * 5)
            return self.current_state, self.state_confidence, feats

        # 2. Locomotion / Walking
        if var > 0.08 or (mean > (baseline + 0.50)) or (her > 0.35 and var > 0.03):
            self.current_state = "LOCOMOTION_WALKING"
            self.state_confidence = min(0.98, 0.5 + var * 2.0)

        # 3. Desk Work / Gestures / Typing
        elif var > 0.008 or (mean > (baseline + 0.20)):
            self.current_state = "DESK_WORK_GESTURES"
            self.state_confidence = 0.85

        # 4. Sedentary Breathing
        elif (mean > (baseline + 0.04)) or (rer > 0.40 and var > 0.001):
            self.current_state = "SEDENTARY_RESPIRATION"
            self.state_confidence = min(0.95, 0.6 + rer * 0.4)

        # 5. Vacant / Static Room Floor
        else:
            self.current_state = "VACANT"
            self.state_confidence = 0.90

        return self.current_state, self.state_confidence, feats
