"""
Bistatic Multi-Node Mesh Trilateration Engine
=============================================
Solves for the Cartesian (X, Y) coordinates of a moving human reflector
using a multi-static mesh of 3 to 4 ESP32 Wi-Fi nodes.

Mathematical Model:
  Each Transmitter-Receiver pair (TX -> Target -> RX_i) forms an ellipsoid of revolution.
  The intersection of 3 confocal ellipses uniquely resolves target coordinates.

Part of the ESP32-S3 Wi-Fi CSI Spatial Radar Project.
"""

import numpy as np
from scipy.optimize import least_squares

class BistaticMeshTrilaterator:
    def __init__(self, tx_pos=(0.0, 0.0), rx_nodes=None, wavelength=0.123):
        """
        tx_pos: (x, y) coordinate of Master Transmitter (meters)
        rx_nodes: Dict of {node_id: (x, y)} for Receiver nodes
        wavelength: 2.437 GHz wavelength in air (~0.123 meters)
        """
        self.tx_pos = np.array(tx_pos, dtype=float)
        self.wavelength = wavelength

        # Default room layout: 4x4 meter space
        if rx_nodes is None:
            self.rx_nodes = {
                'node_1': np.array([4.0, 0.0]),  # Bottom Right
                'node_2': np.array([4.0, 4.0]),  # Top Right
                'node_3': np.array([0.0, 4.0]),  # Top Left
            }
        else:
            self.rx_nodes = {k: np.array(v, dtype=float) for k, v in rx_nodes.items()}

        # Compute baseline Line-of-Sight distances
        self.los_distances = {}
        for nid, pos in self.rx_nodes.items():
            self.los_distances[nid] = np.linalg.norm(pos - self.tx_pos)

    def residuals(self, target_xy, delta_distances):
        """
        Objective function: Residual difference between modeled path distance
        and measured bistatic path distance for each receiver.
        """
        res = []
        d_tx_target = np.linalg.norm(target_xy - self.tx_pos)

        for nid, rx_pos in self.rx_nodes.items():
            if nid in delta_distances:
                d_target_rx = np.linalg.norm(target_xy - rx_pos)
                model_delta = (d_tx_target + d_target_rx) - self.los_distances[nid]
                measured_delta = delta_distances[nid]
                res.append(model_delta - measured_delta)

        return np.array(res)

    def locate(self, delta_distances, initial_guess=(2.0, 2.0), bounds=((0.0, 0.0), (6.0, 6.0))):
        """
        Solve non-linear least squares to pinpoint (X, Y) coordinate.
        delta_distances: Dict of {node_id: measured_delta_meters}
        Returns: (x, y, cost, is_valid)
        """
        if len(delta_distances) < 2:
            return None, None, 999.0, False

        result = least_squares(
            self.residuals,
            x0=np.array(initial_guess),
            bounds=bounds,
            args=(delta_distances,),
            method='trf',
            loss='soft_l1'  # Robust against outlier multipath echoes
        )

        x, y = result.x
        cost = float(result.cost)
        is_valid = bool(result.success and cost < 1.5)
        return x, y, cost, is_valid

    def simulate_measurement(self, true_target_xy, noise_std=0.04):
        """
        Generate synthetic bistatic path length differences for testing.
        """
        target = np.array(true_target_xy)
        d_tx_target = np.linalg.norm(target - self.tx_pos)
        deltas = {}

        for nid, rx_pos in self.rx_nodes.items():
            d_target_rx = np.linalg.norm(target - rx_pos)
            exact_delta = (d_tx_target + d_target_rx) - self.los_distances[nid]
            noise = np.random.normal(0, noise_std)
            deltas[nid] = max(0.01, exact_delta + noise)

        return deltas

if __name__ == "__main__":
    print("Testing 3-Node Bistatic Mesh Trilateration...")
    engine = BistaticMeshTrilaterator(
        tx_pos=(0.0, 0.0),
        rx_nodes={'RX_Alpha': (4.0, 0.0), 'RX_Beta': (4.0, 4.0), 'RX_Gamma': (0.0, 4.0)}
    )

    true_pos = (1.85, 2.40)
    synthetic_deltas = engine.simulate_measurement(true_pos, noise_std=0.03)
    calc_x, calc_y, cost, ok = engine.locate(synthetic_deltas)

    print(f"True Target Position:     ({true_pos[0]:.2f}, {true_pos[1]:.2f}) m")
    print(f"Calculated Target Position: ({calc_x:.2f}, {calc_y:.2f}) m")
    error_cm = np.hypot(calc_x - true_pos[0], calc_y - true_pos[1]) * 100.0
    print(f"Localization Error:       {error_cm:.1f} cm (Residual cost: {cost:.4f})")
    assert error_cm < 25.0, "Localization error exceeds 25cm tolerance"
    print("[+] Bistatic Trilateration Test: PASSED!")
