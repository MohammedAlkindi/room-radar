/*
 * =========================================================================
 * ESP32-S3 High-Speed RF Illuminator Beacon (100 Hz Edition)
 * =========================================================================
 * Transmits continuous 100 Hz ESP-NOW RF pulses on Channel 6 to illuminate
 * the room for CSI spatial radar sensing.
 *
 * Board: ESP32-S3 Dev Module
 */

#include <WiFi.h>
#include <esp_wifi.h>
#include <esp_now.h>

#define WIFI_CHANNEL 6

uint8_t broadcast_mac[] = {0xFF, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF};

struct BeaconPacket {
    uint32_t seq;
    uint32_t uptime_ms;
};

BeaconPacket pkt;

void setup() {
    Serial.begin(115200);
    delay(400);
#if defined(CONFIG_IDF_TARGET_ESP32S3)
    Serial.setTxTimeoutMs(0);
#endif

    Serial.println("\n=======================================================");
    Serial.println("  ESP32-S3 High-Speed RF Illuminator (100 Hz Beacon)   ");
    Serial.println("=======================================================");

    pinMode(2, OUTPUT);
    digitalWrite(2, HIGH); // Visual indicator: Beacon alive

    WiFi.mode(WIFI_STA);
    WiFi.disconnect();
    esp_wifi_start();
    esp_wifi_set_channel(WIFI_CHANNEL, WIFI_SECOND_CHAN_NONE);

    if (esp_now_init() == ESP_OK) {
        esp_now_peer_info_t peerInfo = {};
        memcpy(peerInfo.peer_addr, broadcast_mac, 6);
        peerInfo.channel = WIFI_CHANNEL;
        peerInfo.encrypt = false;
        esp_now_add_peer(&peerInfo);
        Serial.println("[+] ESP-NOW 100 Hz Pulse Illuminator: ACTIVE");
    } else {
        Serial.println("[!] ESP-NOW Init Failed!");
    }
}

void loop() {
    pkt.seq++;
    pkt.uptime_ms = millis();
    esp_now_send(broadcast_mac, (uint8_t*)&pkt, sizeof(pkt));

    static unsigned long lastLog = 0;
    if (millis() - lastLog >= 1000) {
        lastLog = millis();
        Serial.printf("[BEACON] Active · Channel %d · 100 Hz · Seq: %u\n", WIFI_CHANNEL, pkt.seq);
    }
    delay(10); // 100 Hz pulse rate (10ms interval)
}
