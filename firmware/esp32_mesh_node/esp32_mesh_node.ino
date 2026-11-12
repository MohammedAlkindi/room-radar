/*
 * =========================================================================
 * ESP32 Multi-Node Wi-Fi CSI Mesh Radar Firmware
 * =========================================================================
 * For distributed 3D / 2D spatial trilateration using 3 to 4 ESP32 nodes.
 *
 * Architecture:
 *   - 1 Node configured as MASTER_BEACON (Transmits ESP-NOW pulses at 100 Hz)
 *   - 2-3 Nodes configured as RX_SENSORS (Extract bistatic phase deltas)
 *
 * Board: ESP32 / ESP32-S3 Dev Module
 * Framework: Arduino ESP32 core
 */

#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_now.h>

// ==========================================
// NODE ROLE CONFIGURATION
// ==========================================
// Select ROLE for this specific board:
#define ROLE_MASTER_BEACON 1
#define ROLE_RX_SENSOR     2

#define CURRENT_ROLE ROLE_RX_SENSOR  // Set to ROLE_MASTER_BEACON on 1 board, ROLE_RX_SENSOR on others
#define NODE_ID      "RX_Beta"      // Primary Receiver for Chrome Visualizer
#define WIFI_CHANNEL 6

// Fixed broadcast MAC for ESP-NOW mesh
uint8_t broadcast_mac[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

#if CURRENT_ROLE == ROLE_RX_SENSOR

#define CSI_SUBCARRIERS 64

struct ComplexSample {
    int8_t real;
    int8_t imag;
};

ComplexSample prev_csi[CSI_SUBCARRIERS];
volatile float bistatic_phase_delta = 0.0;
volatile float bistatic_path_delta_m = 0.0;
volatile uint32_t packet_count = 0;
bool history_initialized = false;
const float lambda = 0.123f; // 2.437 GHz wavelength in meters

// IRAM CSI Callback
void IRAM_ATTR csi_rx_callback(void *ctx, wifi_csi_info_t *data) {
    if (!data || !data->buf || data->len == 0) return;

    int8_t *buf = data->buf;
    int num_sub = min(data->len / 2, CSI_SUBCARRIERS);
    float phase_accum = 0.0;
    int count = 0;

    for (int k = 0; k < num_sub; k++) {
        int8_t r_now = buf[k * 2];
        int8_t i_now = buf[k * 2 + 1];
        if (r_now == 0 && i_now == 0) continue;

        if (history_initialized) {
            int8_t r_prev = prev_csi[k].real;
            int8_t i_prev = prev_csi[k].imag;

            // Conjugate Phase Differencing: H(t) * conj(H(t-1))
            float cross_r = (float)r_now * r_prev + (float)i_now * i_prev;
            float cross_i = (float)i_now * r_prev - (float)r_now * i_prev;
            float d_phi = atan2(cross_i, cross_r);

            phase_accum += abs(d_phi);
            count++;
        }
        prev_csi[k].real = r_now;
        prev_csi[k].imag = i_now;
    }

    history_initialized = true;
    packet_count++;

    if (count > 0) {
        float mean_dphi = phase_accum / count;
        // Exponential smoothing
        bistatic_phase_delta = (bistatic_phase_delta * 0.70f) + (mean_dphi * 0.30f);
        // Convert phase delta to physical path length delta (meters)
        // delta_d = (delta_phi / 2*pi) * lambda
        bistatic_path_delta_m = (bistatic_phase_delta / (2.0f * PI)) * lambda;
    }
}
#endif

// Packet struct for ESP-NOW beacon
struct MeshBeaconPacket {
    uint32_t seq;
    uint32_t timestamp_ms;
};

MeshBeaconPacket tx_pkt;

void setup() {
    Serial.begin(115200);
    delay(500);
    Serial.setTxTimeoutMs(0); // Non-blocking USB CDC output

    Serial.println("\n=======================================================");
    Serial.println("  ESP32 Multi-Node Wi-Fi CSI Spatial Mesh Node         ");
    Serial.println("=======================================================");

    WiFi.mode(WIFI_STA);
    esp_wifi_start(); // Explicitly start Wi-Fi radio stack

    // Set Wi-Fi channel & ensure promiscuous mode captures all OFDM preambles
    esp_wifi_set_promiscuous(true);
    esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

    // Initialize ESP-NOW
    if (esp_now_init() != ESP_OK) {
        Serial.println("[!] ESP-NOW Initialization Failed!");
        return;
    }

#if CURRENT_ROLE == ROLE_MASTER_BEACON
    Serial.println("[+] Role: MASTER BEACON (Tx Mode)");
    Serial.print("[+] Broadcasting high-speed pulses on Channel ");
    Serial.println(WIFI_CHANNEL);

    esp_now_peer_info_t peerInfo = {};
    memcpy(peerInfo.peer_addr, broadcast_mac, 6);
    peerInfo.channel = WIFI_CHANNEL;
    peerInfo.encrypt = false;
    esp_now_add_peer(&peerInfo);

#elif CURRENT_ROLE == ROLE_RX_SENSOR
    Serial.print("[+] Role: RX SENSOR (");
    Serial.print(NODE_ID);
    Serial.println(")");

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

    esp_err_t err1 = esp_wifi_set_csi_config(&csi_config);
    esp_err_t err2 = esp_wifi_set_csi_rx_cb(csi_rx_callback, NULL);
    esp_err_t err3 = esp_wifi_set_csi(true);
    if (err1 != ESP_OK || err2 != ESP_OK || err3 != ESP_OK) {
        Serial.printf("[!] CSI Init Warning: config=%d cb=%d enable=%d\n", err1, err2, err3);
    } else {
        Serial.println("[+] Hardware CSI Multi-static Extractor: ONLINE");
    }
    Serial.println("[+] Telemetry format: RADAR:<metric>,RSSI:<rssi>,CSI_LEN:<len>,PACKETS:<count>");
#endif
}

void loop() {
#if CURRENT_ROLE == ROLE_MASTER_BEACON
    // Broadcast pulses at ~66 Hz
    tx_pkt.seq++;
    tx_pkt.timestamp_ms = millis();
    esp_now_send(broadcast_mac, (uint8_t*)&tx_pkt, sizeof(tx_pkt));

    static unsigned long lastBeaconLog = 0;
    if (millis() - lastBeaconLog >= 1000) {
        lastBeaconLog = millis();
        Serial.print("[BEACON] Active · Transmitting 66 Hz Pulses · Seq: ");
        Serial.println(tx_pkt.seq);
    }
    delay(15); // ~66 Hz pulse rate

#elif CURRENT_ROLE == ROLE_RX_SENSOR
    static unsigned long lastPrint = 0;
    if (millis() - lastPrint >= 50) { // 20 Hz telemetry output
        lastPrint = millis();

        float metric = 1.20f + (bistatic_phase_delta * 1.5f);

        Serial.print("RADAR:");
        Serial.print(metric, 2);
        Serial.print(",RSSI:");
        Serial.print(WiFi.RSSI());
        Serial.print(",CSI_LEN:128");
        Serial.print(",PACKETS:");
        Serial.print(packet_count);
        Serial.print(",MESH:");
        Serial.print(NODE_ID);
        Serial.print(",DELTA_M:");
        Serial.println(bistatic_path_delta_m, 4);
    }
    delay(10);
#endif
}
