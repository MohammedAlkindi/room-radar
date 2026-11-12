/*
 * =========================================================================
 * ESP32 Multi-Static CSI Master Receiver Engine (Trilateration Edition)
 * =========================================================================
 * Board 1 (Master Desk Receiver on COM15)
 * Captures CSI from multiple distributed beacons (End of Room, Bed, Door)
 * on Channel 6, isolates individual transmitter links, and streams
 * multi-static spatial coordinates (X, Z) to WebGL visualizer.
 *
 * Board: ESP32 Dev Module (WROOM-32U / WROOM-32)
 */

#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_now.h>
#include <math.h>

#define WIFI_CHANNEL 6
#define MAX_SUBCARRIERS 64
#define MAX_NODES 6

struct ComplexSample {
    int8_t real;
    int8_t imag;
};

// Node tracking record
struct NodeTrack {
    uint8_t mac[6];
    uint8_t node_id;
    int8_t last_rssi;
    uint32_t packet_count;
    uint32_t last_seen_ms;
    float phase_metric;
    float amp_metric;
    ComplexSample prev_csi[MAX_SUBCARRIERS];
    bool initialized;
};

NodeTrack nodes[MAX_NODES];
int total_known_nodes = 0;

volatile int8_t isr_csi_buf[128];
volatile uint16_t isr_csi_len = 0;
volatile int8_t isr_rssi = -50;
volatile uint8_t isr_mac[6];
volatile uint32_t isr_packet_count = 0;
volatile bool isr_has_packet = false;

// Packet structure matching our beacons
struct __attribute__((packed)) MeshBeaconPacket {
    uint8_t magic[4];     // 'M', 'E', 'S', 'H'
    uint8_t node_id;      // 2 = End of Room, 3 = Bed, 4 = Door
    uint32_t seq;
    uint32_t uptime_ms;
};

// IRAM CSI ISR: fast copy only, no float operations
void IRAM_ATTR csi_rx_callback(void *ctx, wifi_csi_info_t *data) {
    if (!data || !data->buf || data->len == 0) return;
    int len = data->len > 128 ? 128 : data->len;
    memcpy((void*)isr_csi_buf, data->buf, len);
    memcpy((void*)isr_mac, data->mac, 6);
    isr_csi_len = len;
    isr_rssi = data->rx_ctrl.rssi;
    isr_packet_count++;
    isr_has_packet = true;
}

int find_or_add_node(const uint8_t *mac) {
    for (int i = 0; i < total_known_nodes; i++) {
        if (memcmp(nodes[i].mac, mac, 6) == 0) return i;
    }
    if (total_known_nodes < MAX_NODES) {
        int idx = total_known_nodes++;
        memcpy(nodes[idx].mac, mac, 6);
        nodes[idx].node_id = idx + 2; // Default IDs: 2, 3, 4...
        nodes[idx].packet_count = 0;
        nodes[idx].phase_metric = 0.0f;
        nodes[idx].amp_metric = 0.0f;
        nodes[idx].initialized = false;
        return idx;
    }
    return 0;
}

void setup() {
    Serial.begin(115200);
    delay(400);

    Serial.println("\n=======================================================");
    Serial.println("  ESP32 Multi-Static CSI Master Receiver (Trilateration) ");
    Serial.println("=======================================================");

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    esp_wifi_start();

    // Promiscuous mode on fixed Channel 6 to capture all OFDM CSI preambles
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

    Serial.println("[+] Master CSI Sniffer: ONLINE on Channel 6");
    Serial.println("[+] Listening for Mesh Beacons...");
}

void loop() {
    // 1. Process CSI packets safely in main loop
    if (isr_has_packet) {
        isr_has_packet = false;

        uint8_t cur_mac[6];
        memcpy(cur_mac, (const void*)isr_mac, 6);
        int node_idx = find_or_add_node(cur_mac);
        NodeTrack &node = nodes[node_idx];

        node.last_rssi = isr_rssi;
        node.packet_count++;
        node.last_seen_ms = millis();

        int num_sub = min((int)isr_csi_len / 2, MAX_SUBCARRIERS);
        float amp_diff_accum = 0.0f;
        float phase_diff_accum = 0.0f;
        int valid_cnt = 0;

        for (int k = 0; k < num_sub; k++) {
            int8_t r_now = isr_csi_buf[k * 2];
            int8_t i_now = isr_csi_buf[k * 2 + 1];
            if (r_now == 0 && i_now == 0) continue;

            int amp_now = abs((int)r_now) + abs((int)i_now);

            if (node.initialized) {
                int8_t r_prev = node.prev_csi[k].real;
                int8_t i_prev = node.prev_csi[k].imag;
                int amp_prev = abs((int)r_prev) + abs((int)i_prev);

                amp_diff_accum += abs(amp_now - amp_prev);

                // CFO-Invariant Conjugate Phase Differencing
                float cross_r = (float)r_now * r_prev + (float)i_now * i_prev;
                float cross_i = (float)i_now * r_prev - (float)r_now * i_prev;
                float d_phi = atan2f(cross_i, cross_r);

                phase_diff_accum += fabsf(d_phi);
                valid_cnt++;
            }
            node.prev_csi[k].real = r_now;
            node.prev_csi[k].imag = i_now;
        }

        node.initialized = true;

        if (valid_cnt > 0) {
            float raw_amp_var = amp_diff_accum / valid_cnt;
            float raw_phase_var = phase_diff_accum / valid_cnt;

            node.amp_metric   = (node.amp_metric * 0.70f) + (raw_amp_var * 0.30f);
            node.phase_metric = (node.phase_metric * 0.70f) + (raw_phase_var * 0.30f);
        }
    }

    // 2. Telemetry Output Stream at 25 Hz (40 ms)
    static unsigned long lastTelem = 0;
    if (millis() - lastTelem >= 40) {
        lastTelem = millis();

        // Node 0 -> Link Z (End of Room)
        // Node 1 -> Link X (Bed)
        float varZ = (total_known_nodes > 0) ? (nodes[0].phase_metric * 0.85f + nodes[0].amp_metric * 0.25f) : 0.0f;
        float varX = (total_known_nodes > 1) ? (nodes[1].phase_metric * 0.85f + nodes[1].amp_metric * 0.25f) : 0.0f;
        int rssiZ  = (total_known_nodes > 0) ? nodes[0].last_rssi : -90;
        int rssiX  = (total_known_nodes > 1) ? nodes[1].last_rssi : -90;

        // Stream parsed telemetry for 3D visualizer
        Serial.print("RADAR:");
        Serial.print(1.20f + varZ, 2);
        Serial.print(",RSSI:");
        Serial.print(rssiZ);
        Serial.print(",CSI_LEN:");
        Serial.print(isr_csi_len);
        Serial.print(",PACKETS:");
        Serial.print(isr_packet_count);
        Serial.print(",VAR_Z:");
        Serial.print(varZ, 3);
        Serial.print(",VAR_X:");
        Serial.print(varX, 3);
        Serial.print(",KNOWN_NODES:");
        Serial.println(total_known_nodes);
    }
}
