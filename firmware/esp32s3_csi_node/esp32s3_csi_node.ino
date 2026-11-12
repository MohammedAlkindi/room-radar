/*
 * =========================================================================
 * ESP32-S3 Wi-Fi CSI Advanced Radar Node Firmware v2.0
 * =========================================================================
 * Single-node high-speed biometric & spatial sensing engine.
 * Implements Conjugate Phase Differencing for CFO cancellation and
 * multi-subcarrier amplitude envelope extraction.
 *
 * Board: ESP32-S3 Dev Module
 * Framework: Arduino ESP32 core
 */

#include <WiFi.h>
#include <WiFiUdp.h>
#include "esp_wifi.h"

// Wi-Fi Configuration
const char* ssid     = "YOUR_WIFI_SSID";      // 2.4 GHz network; set before flashing
const char* password = "YOUR_WIFI_PASSWORD";  // never commit a real password

#define CSI_MAX_SUBCARRIERS 64

struct ComplexSample {
    int8_t real;
    int8_t imag;
};

ComplexSample prev_csi[CSI_MAX_SUBCARRIERS];

volatile float csi_amplitude_metric = 0.0;
volatile float csi_phase_metric = 0.0;
volatile uint32_t packet_count = 0;
volatile uint16_t last_csi_len = 0;
bool history_initialized = false;

WiFiUDP udp;
IPAddress targetIP;

void IRAM_ATTR csi_rx_callback(void *ctx, wifi_csi_info_t *data) {
    if (!data || !data->buf || data->len == 0) return;

    last_csi_len = data->len;
    int8_t *buf = data->buf;
    int num_subcarriers = min(data->len / 2, CSI_MAX_SUBCARRIERS);

    float amp_diff_accum = 0.0;
    float phase_diff_accum = 0.0;
    int valid_subcarriers = 0;

    for (int k = 0; k < num_subcarriers; k++) {
        int8_t r_now = buf[k * 2];
        int8_t i_now = buf[k * 2 + 1];
        if (r_now == 0 && i_now == 0) continue;

        int amp_now = (int)sqrt(r_now * r_now + i_now * i_now);

        if (history_initialized) {
            int8_t r_prev = prev_csi[k].real;
            int8_t i_prev = prev_csi[k].imag;
            int amp_prev = (int)sqrt(r_prev * r_prev + i_prev * i_prev);

            // 1. Amplitude Perturbation
            amp_diff_accum += abs(amp_now - amp_prev);

            // 2. Conjugate Phase Differencing (CFO cancellation)
            float cross_real = (float)r_now * r_prev + (float)i_now * i_prev;
            float cross_imag = (float)i_now * r_prev - (float)r_now * i_prev;
            float phase_diff = atan2(cross_imag, cross_real);

            phase_diff_accum += abs(phase_diff);
            valid_subcarriers++;
        }

        prev_csi[k].real = r_now;
        prev_csi[k].imag = i_now;
    }

    history_initialized = true;
    packet_count++;

    if (valid_subcarriers > 0) {
        float raw_amp_var = amp_diff_accum / valid_subcarriers;
        float raw_phase_var = phase_diff_accum / valid_subcarriers;

        csi_amplitude_metric = (csi_amplitude_metric * 0.70f) + (raw_amp_var * 0.30f);
        csi_phase_metric     = (csi_phase_metric * 0.70f) + (raw_phase_var * 0.30f);
    }
}

void setup() {
    Serial.begin(115200);

    unsigned long start = millis();
    while (!Serial && millis() - start < 3000) delay(10);

    Serial.println("\n=======================================================");
    Serial.println("  ESP32-S3 Wi-Fi CSI Radar v2.0 (Phase-Differenced)    ");
    Serial.println("=======================================================");

    WiFi.mode(WIFI_STA);
    WiFi.begin(ssid, password);

    Serial.print("[*] Connecting to [");
    Serial.print(ssid);
    Serial.print("]");

    int timeout = 0;
    while (WiFi.status() != WL_CONNECTED && timeout < 40) {
        delay(300);
        Serial.print(".");
        timeout++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("\n[+] Wi-Fi Connected!");
        Serial.print("[+] Node IP: ");
        Serial.println(WiFi.localIP());
        targetIP = WiFi.gatewayIP();
    } else {
        Serial.println("\n[!] Hotspot connection failed.");
    }

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

    ESP_ERROR_CHECK(esp_wifi_set_csi_config(&csi_config));
    ESP_ERROR_CHECK(esp_wifi_set_csi_rx_cb(csi_rx_callback, NULL));
    ESP_ERROR_CHECK(esp_wifi_set_csi(true));

    Serial.println("[+] Hardware CSI Matrix Extractor: ONLINE");
    Serial.println("[+] Telemetry format: RADAR:<metric>,RSSI:<rssi>,CSI_LEN:<len>,PACKETS:<count>");
}

void loop() {
    if (WiFi.status() == WL_CONNECTED) {
        udp.beginPacket(targetIP, 8888);
        udp.write('A');
        udp.endPacket();
    }

    static unsigned long lastPrint = 0;
    if (millis() - lastPrint >= 60) {
        lastPrint = millis();

        float fused_metric = csi_amplitude_metric + (csi_phase_metric * 0.40f);

        Serial.print("RADAR:");
        Serial.print(fused_metric, 2);
        Serial.print(",RSSI:");
        Serial.print(WiFi.RSSI());
        Serial.print(",CSI_LEN:");
        Serial.print(last_csi_len);
        Serial.print(",PACKETS:");
        Serial.println(packet_count);
    }

    delay(20);
}
