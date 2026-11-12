/*
 * =========================================================================
 * ESP32-S3 High-Speed Direct CSI Radar Engine (Zero-Latency Edition)
 * =========================================================================
 * Ultra-low latency (25 Hz / 40ms) standalone spatial sensing engine.
 * Self-generates 50 Hz RF pulses on Channel 6, captures subcarrier CSI,
 * and outputs real-time metric streams for the 3D Kinematic Visualizer.
 *
 * Board: ESP32-S3 Dev Module
 * Framework: Arduino ESP32 core
 */

#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_now.h>
#include <math.h>

#define CSI_MAX_SUBCARRIERS 64
#define WIFI_CHANNEL 6

struct ComplexSample {
    int8_t real;
    int8_t imag;
};

ComplexSample prev_csi[CSI_MAX_SUBCARRIERS];

volatile int8_t raw_csi_buf[128];
volatile uint16_t last_csi_len = 128;
volatile int8_t last_rssi = -38;
volatile uint32_t packet_count = 0;
volatile bool has_new_packet = false;

float csi_amplitude_metric = 0.0f;
float csi_phase_metric = 0.0f;
bool history_initialized = false;

// 802.11 Action frame beacon packet for continuous channel illumination
uint8_t pulse_packet[32] = {
    0xd0, 0x00, 0x00, 0x00,                         // Frame Control & Duration
    0xff, 0xff, 0xff, 0xff, 0xff, 0xff,             // Destination: Broadcast
    0x30, 0xae, 0xa4, 0x11, 0x22, 0x33,             // Source: Local MAC
    0x30, 0xae, 0xa4, 0x11, 0x22, 0x33,             // BSSID: Local MAC
    0x00, 0x00,                                     // Sequence Control
    0x7f, 0x18, 0x01, 0x02, 0x03, 0x04              // Payload
};

// Zero-crash callback: ONLY copies bytes in ISR; NO floating-point or Flash calls!
void csi_rx_callback(void *ctx, wifi_csi_info_t *data) {
    if (!data || !data->buf || data->len == 0) return;
    int len = data->len > 128 ? 128 : data->len;
    memcpy((void*)raw_csi_buf, data->buf, len);
    last_csi_len = len;
    last_rssi = data->rx_ctrl.rssi;
    packet_count++;
    has_new_packet = true;
}

void setup() {
    Serial.begin(115200);
    delay(400);
#if defined(CONFIG_IDF_TARGET_ESP32S3)
    Serial.setTxTimeoutMs(0); // Non-blocking CDC write
#endif

    Serial.println("\n=======================================================");
    Serial.println("  ESP32-S3 High-Speed Direct CSI Radar (Zero-Latency)   ");
    Serial.println("=======================================================");

    WiFi.mode(WIFI_STA);
    esp_wifi_start();

    // Enable promiscuous mode on fixed Channel 6
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

    wifi_csi_config_t csi_config = {
        .lltf_en           = 1,
        .htltf_en          = 1,
        .stbc_htltf2_en    = 1,
        .ltf_merge_en      = 1,
        .channel_filter_en = 0,
        .manu_scale        = 0,
        .shift             = 0,
        .dump_ack_en       = 1,
    };

    esp_wifi_set_csi_config(&csi_config);
    esp_wifi_set_csi_rx_cb(csi_rx_callback, NULL);
    esp_wifi_set_csi(true);

    Serial.println("[+] CSI Engine ONLINE · Channel 6 · 25 Hz Output");
    Serial.println("[+] Streaming RADAR format to Serial CDC...");
}

void loop() {
    // 1. Transmit 50 Hz RF pulses to illuminate the room
    static unsigned long lastPulse = 0;
    if (millis() - lastPulse >= 20) { // 50 Hz pulse rate
        lastPulse = millis();
        pulse_packet[22]++; // Increment sequence
        esp_wifi_80211_tx(WIFI_IF_STA, pulse_packet, sizeof(pulse_packet), false);
    }

    // 2. Safe DSP Processing in loop() (FPU & Flash memory safe)
    if (has_new_packet) {
        has_new_packet = false;
        int num_subcarriers = min((int)last_csi_len / 2, CSI_MAX_SUBCARRIERS);
        float amp_diff_accum = 0.0f;
        float phase_diff_accum = 0.0f;
        int valid_subcarriers = 0;

        for (int k = 0; k < num_subcarriers; k++) {
            int8_t r_now = raw_csi_buf[k * 2];
            int8_t i_now = raw_csi_buf[k * 2 + 1];
            if (r_now == 0 && i_now == 0) continue;

            int amp_now = abs((int)r_now) + abs((int)i_now);

            if (history_initialized) {
                int8_t r_prev = prev_csi[k].real;
                int8_t i_prev = prev_csi[k].imag;
                int amp_prev = abs((int)r_prev) + abs((int)i_prev);

                amp_diff_accum += abs(amp_now - amp_prev);

                // Conjugate phase difference (CFO-invariant Doppler)
                float cross_r = (float)r_now * r_prev + (float)i_now * i_prev;
                float cross_i = (float)i_now * r_prev - (float)r_now * i_prev;
                float d_phi = atan2f(cross_i, cross_r);

                phase_diff_accum += fabsf(d_phi);
                valid_subcarriers++;
            }
            prev_csi[k].real = r_now;
            prev_csi[k].imag = i_now;
        }

        history_initialized = true;

        if (valid_subcarriers > 0) {
            float raw_amp_var = amp_diff_accum / valid_subcarriers;
            float raw_phase_var = phase_diff_accum / valid_subcarriers;

            // Fast EMA tracking (alpha = 0.35)
            csi_amplitude_metric = (csi_amplitude_metric * 0.65f) + (raw_amp_var * 0.35f);
            csi_phase_metric     = (csi_phase_metric * 0.65f) + (raw_phase_var * 0.35f);
        }
    }

    // 3. Guaranteed 25 Hz Real-Time Telemetry to USB CDC (40ms latency)
    static unsigned long lastTelemetry = 0;
    if (millis() - lastTelemetry >= 40) {
        lastTelemetry = millis();

        float fused_metric = 1.20f + (csi_amplitude_metric * 0.22f) + (csi_phase_metric * 0.85f);

        Serial.print("RADAR:");
        Serial.print(fused_metric, 2);
        Serial.print(",RSSI:");
        Serial.print(last_rssi);
        Serial.print(",CSI_LEN:");
        Serial.print(last_csi_len);
        Serial.print(",PACKETS:");
        Serial.println(packet_count);
    }
}
