/**
 * ==============================================================================
 * HLK-LD2450 24GHz FMCW mmWave Radar + ESP32-S3 Multi-Target Cartesian Tracker
 * ==============================================================================
 * 
 * Hardware Required:
 * 1. ESP32-S3 Dev Board
 * 2. HLK-LD2450 24GHz mmWave Radar Sensor (~$8-12)
 * 
 * Wiring:
 *   HLK-LD2450 VCC  ---> ESP32-S3 5V (or VBUS / VIN)
 *   HLK-LD2450 GND  ---> ESP32-S3 GND
 *   HLK-LD2450 TX   ---> ESP32-S3 GPIO 18 (Serial1 RX)
 *   HLK-LD2450 RX   ---> ESP32-S3 GPIO 17 (Serial1 TX)
 * 
 * Features:
 * - Tracks up to 3 people simultaneously
 * - Outputs exact Cartesian coordinates: X (-6m to +6m), Y (0m to 6m)
 * - Measures radial speed (cm/s) and distance resolution
 * - Streams clean JSON over native USB Serial for the 2D Web Visualizer
 */

#define RADAR_RX_PIN 18
#define RADAR_TX_PIN 17
#define RADAR_BAUD   256000

HardwareSerial RadarSerial(1);

const byte FRAME_HEADER[4] = { 0xAA, 0xFF, 0x03, 0x00 };
const byte FRAME_TAIL[2]   = { 0x55, 0xCC };

struct TargetData {
    int16_t x;       // X coordinate in mm (negative = left, positive = right)
    int16_t y;       // Y coordinate in mm (distance from radar)
    int16_t speed;   // Speed in cm/s (positive = moving away, negative = moving towards)
    uint16_t res;    // Distance resolution in mm
    bool valid;      // True if a target is actively tracked
};

TargetData targets[3];

void setup() {
    Serial.begin(115200);
    while (!Serial && millis() < 3000) delay(10);

    Serial.println("\n=======================================================");
    Serial.println("  ESP32-S3 + HLK-LD2450 24GHz mmWave Cartesian Tracker ");
    Serial.println("=======================================================");

    RadarSerial.begin(RADAR_BAUD, SERIAL_8N1, RADAR_RX_PIN, RADAR_TX_PIN);

    Serial.println("[+] Radar UART initialized at 256000 baud");
    Serial.println("[+] Waiting for 24GHz FMCW frames...");
}

void parseTarget(byte* data, TargetData &t) {
    uint16_t raw_x = data[0] | (data[1] << 8);
    uint16_t raw_y = data[2] | (data[3] << 8);
    uint16_t raw_speed = data[4] | (data[5] << 8);
    uint16_t raw_res = data[6] | (data[7] << 8);

    t.x = (raw_x & 0x8000) ? -(int16_t)(raw_x & 0x7FFF) : (int16_t)(raw_x & 0x7FFF);
    t.y = (raw_y & 0x8000) ? -(int16_t)(raw_y & 0x7FFF) : (int16_t)(raw_y & 0x7FFF);
    t.speed = (raw_speed & 0x8000) ? -(int16_t)(raw_speed & 0x7FFF) : (int16_t)(raw_speed & 0x7FFF);
    t.res = raw_res;

    t.valid = (t.y > 0 && t.y < 8000 && t.res > 0);
}

void loop() {
    static byte buffer[64];
    static int bufIdx = 0;

    while (RadarSerial.available()) {
        byte b = RadarSerial.read();

        if (bufIdx < 4) {
            if (b == FRAME_HEADER[bufIdx]) {
                buffer[bufIdx++] = b;
            } else {
                bufIdx = 0;
                if (b == FRAME_HEADER[0]) buffer[bufIdx++] = b;
            }
        } else {
            buffer[bufIdx++] = b;

            if (bufIdx == 30) {
                if (buffer[28] == FRAME_TAIL[0] && buffer[29] == FRAME_TAIL[1]) {
                    parseTarget(&buffer[4],  targets[0]);
                    parseTarget(&buffer[12], targets[1]);
                    parseTarget(&buffer[20], targets[2]);

                    printTargetJSON();
                }
                bufIdx = 0;
            }
        }
    }
}

void printTargetJSON() {
    static unsigned long lastOutput = 0;
    if (millis() - lastOutput < 50) return;
    lastOutput = millis();

    Serial.print("RADAR_CARTESIAN:{");
    Serial.print("\"targets\":[");
    bool first = true;
    for (int i = 0; i < 3; i++) {
        if (targets[i].valid) {
            if (!first) Serial.print(",");
            Serial.print("{\"id\":");
            Serial.print(i + 1);
            Serial.print(",\"x\":");
            Serial.print(targets[i].x);
            Serial.print(",\"y\":");
            Serial.print(targets[i].y);
            Serial.print(",\"speed\":");
            Serial.print(targets[i].speed);
            Serial.print(",\"res\":");
            Serial.print(targets[i].res);
            Serial.print("}");
            first = false;
        }
    }
    Serial.println("]}");
}
