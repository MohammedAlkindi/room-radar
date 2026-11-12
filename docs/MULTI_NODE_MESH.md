# Multi-Node Wi-Fi CSI Mesh Trilateration

## 1. System Topology & Node Placement
To achieve unambiguous 2D Cartesian $(X, Y)$ coordinate tracking in an indoor room without cameras, a multi-static geometry of **4 ESP32 nodes** is deployed:

```
(0, 4m) Node 3 [RX_Gamma] ----------------------- Node 2 [RX_Beta] (4m, 4m)
        |                                                  |
        |                      TARGET                      |
        |                    (X=1.8m, Y=2.4m)              |
        |                          *                       |
        |                                                  |
(0, 0)  Node 0 [MASTER_TX] ----------------------- Node 1 [RX_Alpha] (4m, 0)
```

### Roles:
- **Node 0 (Master Beacon):** Placed at the origin $(0, 0)$. Broadcasts unencrypted ESP-NOW pulses at 66–100 packets/sec on fixed Wi-Fi Channel 6.
- **Node 1 (RX Alpha):** Placed at bottom-right $(4.0\text{ m}, 0.0\text{ m})$.
- **Node 2 (RX Beta):** Placed at top-right $(4.0\text{ m}, 4.0\text{ m})$.
- **Node 3 (RX Gamma):** Placed at top-left $(0.0\text{ m}, 4.0\text{ m})$.

---

## 2. Mathematical Optimization Pipeline
Each receiver node $i$ captures the transmitted beacon and extracts the bistatic path difference $\Delta d_i(t)$:

$$\Delta d_i(t) = \frac{\Delta \phi_i(t) \cdot \lambda}{2\pi}$$

Where:
$$\Delta d_i = \left( \| \mathbf{p}_{\text{target}} - \mathbf{p}_{TX} \| + \| \mathbf{p}_{\text{target}} - \mathbf{p}_{RX_i} \| \right) - \| \mathbf{p}_{RX_i} - \mathbf{p}_{TX} \|$$

For 3 receiver nodes, this creates a system of 3 non-linear confocal ellipsoidal equations:

$$r_1(x, y) = \sqrt{x^2 + y^2} + \sqrt{(x - 4)^2 + y^2} - 4.0 - \Delta d_1 = 0$$

$$r_2(x, y) = \sqrt{x^2 + y^2} + \sqrt{(x - 4)^2 + (y - 4)^2} - 5.657 - \Delta d_2 = 0$$

$$r_3(x, y) = \sqrt{x^2 + y^2} + \sqrt{x^2 + (y - 4)^2} - 4.0 - \Delta d_3 = 0$$

### Solver: Trust-Region Reflective Least Squares with Soft-L1 Loss
Because multipath echoes in a room occasionally introduce outlier distance estimates, standard squared-error loss ($\sum r_i^2$) suffers from distortion.
The Python solver implements **Soft-L1 loss**:

$$\rho(r) = 2 \left( \sqrt{1 + r^2} - 1 \right)$$

This penalizes large outlier residuals linearly rather than quadratically, preserving sub-10 cm spatial localization precision even in the presence of secondary wall reflections.
