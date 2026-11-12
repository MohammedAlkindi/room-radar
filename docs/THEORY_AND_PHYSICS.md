# Physical Principles & Electromagnetic Wave Theory of Wi-Fi CSI Radar

## 1. Physical Layer Channel Frequency Response (CFR)
In IEEE 802.11a/g/n/ac/ax Orthogonal Frequency-Division Multiplexing (OFDM), a single high-speed radio channel is subdivided into multiple orthogonal subcarriers (52 data subcarriers in a 20 MHz channel; 108 in 40 MHz HT40).

The transmission channel can be modeled as a linear time-variant filter with impulse response:

$$h(t, \tau) = \sum_{p=1}^{P} a_p(t) e^{-j \theta_p(t)} \delta(\tau - \tau_p(t))$$

Where:
- $P$ is the total number of multipath propagation paths (direct LoS, wall bounces, ceiling, furniture, human bodies)
- $a_p(t)$ is the attenuation of the $p$-th path
- $\tau_p(t)$ is the propagation delay of the $p$-th path
- $\theta_p(t)$ is the phase shift along the $p$-th path

Applying the Fourier Transform converts this into the frequency domain, giving the **Channel Frequency Response (CFR)** captured by the ESP32 as Channel State Information (CSI):

$$H(f_k, t) = \sum_{p=1}^{P} a_p(t) e^{-j 2\pi f_k \tau_p(t)}$$

For subcarrier $k \in [-26, 26]$, the measured complex number is:

$$H_k = I_k + j Q_k = |H_k| e^{j \angle H_k}$$

Where $|H_k| = \sqrt{I_k^2 + Q_k^2}$ is the subcarrier amplitude, and $\angle H_k = \text{atan2}(Q_k, I_k)$ is the raw phase.

---

## 2. Static vs. Dynamic Multipath Decomposition
In an indoor room, the vast majority of multipath reflections originate from static boundaries (walls, floor, ceiling, stationary desks). A moving or breathing human body introduces a time-varying dynamic perturbation:

$$H_k(t) = H_{k, \text{static}} + H_{k, \text{dynamic}}(t)$$

$$H_k(t) = H_{k, \text{static}} + \alpha_h(t) e^{-j \frac{2\pi}{\lambda} d_h(t)}$$

Where:
- $\lambda = \frac{c}{f_c} \approx \frac{3 \times 10^8}{2.437 \times 10^9} = 0.123\text{ m}$ (for Channel 6)
- $d_h(t)$ is the total round-trip path length from Transmitter $\to$ Human Body $\to$ Receiver.

Because $H_{k, \text{static}}$ is constant over short time horizons, subtracting the running ambient baseline ($\tilde{H}_k(t) = H_k(t) - \bar{H}_k$) completely eliminates static furniture and structural multipath, leaving **only the human reflector's motion vector**.

---

## 3. Fresnel Zone Diffraction & Knife-Edge Physics
Radio frequency waves propagate between the transmitter ($TX$) and receiver ($RX$) through a series of concentric ellipsoid volumes known as **Fresnel Zones**.

The $n$-th Fresnel zone boundary satisfies the condition that the path length difference between the scattered path and direct Line-of-Sight ($d_{LoS}$) is an integer multiple of half-wavelengths:

$$d_{TX \to P} + d_{P \to RX} - d_{LoS} = n \frac{\lambda}{2}$$

At any point along the LoS axis where distances to $TX$ and $RX$ are $d_1$ and $d_2$ respectively, the radius $r_n$ of the $n$-th Fresnel ellipsoid is:

$$r_n = \sqrt{\frac{n \cdot \lambda \cdot d_1 \cdot d_2}{d_1 + d_2}}$$

### Physical Significance:
- **1st Fresnel Zone ($n = 1$):** Accounts for over 85% of total transferred RF power. At midpoint ($d_1 = d_2 = 2.5\text{ m}$ for a 5-meter link), $r_1 \approx 0.392\text{ m}$. Any object entering this cylinder causes primary phase disturbance.
- **Interference Oscillation:** Moving from the 1st Fresnel zone boundary to the 2nd Fresnel zone boundary changes the phase of the reflected wave by $180^\circ$ ($\pi$ radians). As a person walks across successive Fresnel boundaries, the received signal oscillates between constructive and destructive interference, creating sinusoidal Doppler bursts.

---

## 4. Micro-Doppler Respiration Mechanics
During respiration, the thoracic and abdominal walls expand and contract periodically. The displacement $x(t)$ of the chest wall is modeled as:

$$x(t) = A_r \sin(2\pi f_r t)$$

Where $A_r \approx 3 - 6\text{ mm}$, and $f_r \approx 0.15 - 0.45\text{ Hz}$ ($9 - 27\text{ BPM}$).

The resulting change in total propagation path length is $\Delta d(t) = 2 x(t) \cos \psi$ (where $\psi$ is the reflection angle).
The induced phase rotation is:

$$\Delta \phi(t) = \frac{2\pi}{\lambda} \Delta d(t) = \frac{4\pi A_r \cos \psi}{\lambda} \sin(2\pi f_r t)$$

For $\lambda = 12.3\text{ cm}$ and $A_r = 5\text{ mm}$ with near-normal incidence ($\cos \psi \approx 1$):

$$\Delta \phi_{\text{peak}} = \frac{4 \pi \cdot 0.005}{0.123} \approx 0.511\text{ radians} \approx 29.3^\circ$$

This $29.3^\circ$ phase swing is well above the thermal noise threshold of the ESP32-S3 radio ($\approx 2^\circ - 3^\circ$), enabling high signal-to-noise ratio (SNR) vital sign tracking.

---

## 5. Phase Sanitization & CFO Cancellation
Raw phase on commercial off-the-shelf (COTS) microcontrollers is heavily corrupted by:
1. **Carrier Frequency Offset (CFO):** Clock frequency mismatch between $TX$ and $RX$ oscillators ($\Delta f \approx 10 - 50\text{ kHz}$), causing a rapid phase rotation of tens of radians per second.
2. **Sampling Frequency Offset (SFO):** ADC sampling clock jitter, introducing a linear slope across subcarriers.
3. **Packet Detection Delay (PDD):** Random time-tagging jitter at packet boundaries.

### Solution: Conjugate Differencing
Instead of relying on absolute phase, the firmware computes temporal **Conjugate Phase Differencing** between consecutive packets $t$ and $t-1$:

$$Z_k(t) = H_k(t) \cdot H_k^*(t-1)$$

$$Z_k(t) = |H_k(t)| |H_k(t-1)| \cdot e^{j(\theta_k(t) - \theta_k(t-1))}$$

Because CFO affects all subcarriers and packets equally over millisecond time intervals, the common-mode clock phase rotation cancels out:

$$\Delta \theta_k(t) = \angle Z_k(t) = \text{atan2}\left(\text{Im}(Z_k), \text{Re}(Z_k)\right)$$

This isolates the true physical velocity vector of the dynamic reflector without requiring hardware-synchronized clocks.
