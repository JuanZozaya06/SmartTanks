#include <DNSServer.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <Preferences.h>
#include <WebServer.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include <esp_mac.h>
#include <math.h>

#include "certificates.h"
#include "arduino_secrets.h"

// La red temporal es única por equipo; su nombre y clave se incluyen en el QR
// de instalación de la unidad terminada.
constexpr char AP_PREFIX[] = "SmartTank-";

constexpr char PREF_NAMESPACE[] = "smarttank";
constexpr char PREF_WIFI_SSID[] = "wifiSsid";
constexpr char PREF_WIFI_PASSWORD[] = "wifiPassword";

constexpr uint16_t DNS_PORT = 53;
constexpr uint32_t WIFI_CONNECT_TIMEOUT_MS = 20'000;
constexpr uint32_t READING_INTERVAL_MS = 30'000;
constexpr uint32_t SYNC_INTERVAL_MS = 8'000;
constexpr uint16_t MAX_QUEUED_BATCHES = 120;
constexpr char API_BASE_URL[] = "https://us-east1-smarttanks-830ba.cloudfunctions.net/api";
constexpr char PREF_SEQUENCE[] = "sequence";
constexpr char QUEUE_PATH[] = "/readings.csv";
constexpr char QUEUE_TEMP_PATH[] = "/readings.tmp";

DNSServer dnsServer;
WebServer server(80);
Preferences preferences;

String accessPointName;
String accessPointPassword;
String savedSsid;
String savedPassword;
String connectionMessage = "Aún no se ha configurado una red Wi-Fi.";
String stableDeviceId;
String bootSessionId;
uint32_t lastReadingAt = 0;
uint32_t lastSyncAt = 0;

String deviceIdFromEfuse() {
  uint8_t mac[6];
  esp_read_mac(mac, ESP_MAC_WIFI_STA);
  char identifier[28];
  snprintf(
    identifier,
    sizeof(identifier),
    "smarttank-%02x%02x%02x%02x%02x%02x",
    mac[0], mac[1], mac[2], mac[3], mac[4], mac[5]
  );
  return String(identifier);
}

String deviceSuffix() {
  return stableDeviceId.substring(stableDeviceId.length() - 4);
}

String htmlEscape(const String& value) {
  String escaped;

  for (size_t index = 0; index < value.length(); ++index) {
    const char character = value.charAt(index);
    switch (character) {
      case '&': escaped += "&amp;"; break;
      case '<': escaped += "&lt;"; break;
      case '>': escaped += "&gt;"; break;
      case '"': escaped += "&quot;"; break;
      case '\'': escaped += "&#39;"; break;
      default: escaped += character; break;
    }
  }

  return escaped;
}

String statusHtml() {
  if (WiFi.status() == WL_CONNECTED) {
    return "<p class='ok'><strong>Wi-Fi conectado</strong><br>"
           "Red: " + htmlEscape(WiFi.SSID()) + "<br>"
           "IP local: " + WiFi.localIP().toString() + "<br>"
           "Señal: " + String(WiFi.RSSI()) + " dBm</p>";
  }

  return "<p class='warning'><strong>Wi-Fi no conectado</strong><br>" +
         htmlEscape(connectionMessage) + "</p>";
}

void handleRoot() {
  String page = R"rawliteral(
<!doctype html>
<html lang="es">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>SmartTank · Configuración</title>
  <style>
    body { background:#f5f7fa; color:#132238; font-family:Arial,sans-serif; margin:0; }
    main { background:#fff; box-sizing:border-box; margin:24px auto; max-width:480px; padding:28px; }
    h1 { margin-top:0; }
    label { display:block; font-weight:bold; margin-top:18px; }
    input { box-sizing:border-box; font-size:16px; margin-top:6px; padding:12px; width:100%; }
    button { background:#1565c0; border:0; color:#fff; cursor:pointer; font-size:16px; margin-top:22px; padding:12px; width:100%; }
    .ok { background:#e8f5e9; padding:12px; }
    .warning { background:#fff3e0; padding:12px; }
    .muted { color:#52647a; font-size:14px; }
    form.inline { margin-top:8px; }
    form.inline button { background:#65758b; margin-top:8px; }
  </style>
</head>
<body>
  <main>
    <h1>SmartTank</h1>
    <p>Configura la red Wi-Fi de la casa para conectar el dispositivo.</p>
)rawliteral";

  page += statusHtml();
  page += R"rawliteral(
    <form action="/wifi" method="post">
      <label for="ssid">Nombre de la red Wi-Fi</label>
      <input id="ssid" name="ssid" type="text" maxlength="32" required autocomplete="wifi ssid" placeholder="Ejemplo: MiCasa">

      <label for="password">Contraseña Wi-Fi</label>
      <input id="password" name="password" type="password" maxlength="63" required autocomplete="current-password" placeholder="Contraseña">

      <button type="submit">Guardar y conectar</button>
    </form>

    <form class="inline" action="/wifi/reset" method="post">
      <button type="submit">Olvidar red guardada</button>
    </form>

    <p class="muted">Portal local: 192.168.4.1</p>
  </main>
</body>
</html>
)rawliteral";

  server.send(200, "text/html; charset=utf-8", page);
}

void attemptWifiConnection() {
  if (savedSsid.isEmpty()) {
    connectionMessage = "Aún no se ha configurado una red Wi-Fi.";
    return;
  }

  WiFi.disconnect(false, false);
  delay(100);

  Serial.print("Intentando conectar a Wi-Fi: ");
  Serial.println(savedSsid);

  WiFi.begin(savedSsid.c_str(), savedPassword.c_str());
  const uint32_t startedAt = millis();

  while (WiFi.status() != WL_CONNECTED && millis() - startedAt < WIFI_CONNECT_TIMEOUT_MS) {
    delay(250);
  }

  if (WiFi.status() == WL_CONNECTED) {
    connectionMessage = "Wi-Fi conectado correctamente.";
    Serial.print("Wi-Fi conectado. IP local: ");
    Serial.println(WiFi.localIP());
  } else {
    connectionMessage = "No fue posible conectarse. Revisa el nombre y la contraseña.";
    Serial.println("No fue posible conectar al Wi-Fi guardado.");
  }
}

void handleSaveWifi() {
  const String submittedSsid = server.arg("ssid");
  const String submittedPassword = server.arg("password");

  if (submittedSsid.isEmpty() || submittedPassword.isEmpty()) {
    server.send(400, "text/plain; charset=utf-8", "Falta el nombre o la contraseña de Wi-Fi.");
    return;
  }

  preferences.putString(PREF_WIFI_SSID, submittedSsid);
  preferences.putString(PREF_WIFI_PASSWORD, submittedPassword);

  savedSsid = submittedSsid;
  savedPassword = submittedPassword;
  attemptWifiConnection();

  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "");
}

void handleResetWifi() {
  preferences.remove(PREF_WIFI_SSID);
  preferences.remove(PREF_WIFI_PASSWORD);

  savedSsid = "";
  savedPassword = "";
  WiFi.disconnect(false, false);
  connectionMessage = "La red Wi-Fi guardada fue eliminada.";

  server.sendHeader("Location", "/");
  server.send(303, "text/plain", "");
}

void handleStatus() {
  String json = "{";
  json += "\"deviceId\":\"" + stableDeviceId + "\",";
  json += "\"accessPoint\":\"" + accessPointName + "\",";
  json += "\"portalIp\":\"" + WiFi.softAPIP().toString() + "\",";
  json += "\"connected\":" + String(WiFi.status() == WL_CONNECTED ? "true" : "false");

  if (WiFi.status() == WL_CONNECTED) {
    json += ",\"ssid\":\"" + WiFi.SSID() + "\",";
    json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
    json += "\"rssi\":" + String(WiFi.RSSI());
  }

  json += "}";
  server.send(200, "application/json", json);
}

uint32_t nextSequence() {
  const uint32_t next = preferences.getUInt(PREF_SEQUENCE, 0) + 1;
  preferences.putUInt(PREF_SEQUENCE, next);
  return next;
}

float clampPercentage(float value) {
  return constrain(value, 2.0f, 98.0f);
}

uint16_t queuedBatchCount() {
  File queue = LittleFS.open(QUEUE_PATH, FILE_READ);
  if (!queue) return 0;

  uint16_t count = 0;
  while (queue.available() && count < MAX_QUEUED_BATCHES) {
    queue.readStringUntil('\n');
    ++count;
  }
  queue.close();
  return count;
}

void appendMockBatch() {
  // Conservamos los datos más antiguos hasta recibir confirmación del API.
  // Si la cola llega al límite, se descarta esta nueva muestra, no una pendiente.
  if (queuedBatchCount() >= MAX_QUEUED_BATCHES) {
    Serial.println("COLA LLENA: se conserva la información pendiente y se omite esta muestra.");
    return;
  }
  const uint32_t sequence = nextSequence();
  // Sustituiremos estos valores por las lecturas TM7711 al conectar sensores.
  const float tankA = clampPercentage(65.0f + 20.0f * sinf(sequence * 0.15f));
  const float tankB = clampPercentage(45.0f + 25.0f * sinf(sequence * 0.10f + 1.0f));

  File queue = LittleFS.open(QUEUE_PATH, FILE_APPEND);
  if (!queue) {
    Serial.println("ERROR: no se pudo abrir la cola local.");
    return;
  }
  queue.printf("%lu,%lu,%.2f,%.2f\n", sequence, millis(), tankA, tankB);
  queue.close();
  Serial.printf("Mock guardado: secuencia %lu | A %.1f%% | B %.1f%%\n", sequence, tankA, tankB);
}

bool popFirstQueuedBatch() {
  File source = LittleFS.open(QUEUE_PATH, FILE_READ);
  if (!source) return false;
  source.readStringUntil('\n');
  File destination = LittleFS.open(QUEUE_TEMP_PATH, FILE_WRITE);
  if (!destination) {
    source.close();
    return false;
  }
  while (source.available()) destination.println(source.readStringUntil('\n'));
  source.close();
  destination.close();
  LittleFS.remove(QUEUE_PATH);
  return LittleFS.rename(QUEUE_TEMP_PATH, QUEUE_PATH);
}

String makeReadingsPayload(uint32_t sequence, uint32_t elapsedMs, float tankA, float tankB) {
  const float heightA = tankA * 2.0f;  // prototipo: tanque de 200 cm
  const float heightB = tankB * 2.0f;
  const float litersA = 408.6f * tankA / 100.0f;
  const float litersB = 408.6f * tankB / 100.0f;
  const float pressureA = (heightA / 100.0f) * 9.80665f;
  const float pressureB = (heightB / 100.0f) * 9.80665f;
  char payload[850];
  snprintf(payload, sizeof(payload),
    "{\"deviceId\":\"%s\",\"bootSessionId\":\"%s\",\"readings\":["
    "{\"sequence\":%lu,\"tankChannel\":\"A\",\"timestampQuality\":\"pending\",\"elapsedMs\":%lu,\"pressureKpa\":%.3f,\"waterHeightCm\":%.2f,\"percentage\":%.2f,\"liters\":%.2f,\"wifiRssi\":%d},"
    "{\"sequence\":%lu,\"tankChannel\":\"B\",\"timestampQuality\":\"pending\",\"elapsedMs\":%lu,\"pressureKpa\":%.3f,\"waterHeightCm\":%.2f,\"percentage\":%.2f,\"liters\":%.2f,\"wifiRssi\":%d}]}",
    stableDeviceId.c_str(), bootSessionId.c_str(), sequence, elapsedMs, pressureA, heightA, tankA, litersA, WiFi.RSSI(),
    sequence, elapsedMs, pressureB, heightB, tankB, litersB, WiFi.RSSI());
  return String(payload);
}

void syncFirstQueuedBatch() {
  if (WiFi.status() != WL_CONNECTED) return;
  if (strlen(SMARTTANKS_DEVICE_SECRET) < 16) {
    Serial.println("API: falta un secreto válido en arduino_secrets.h.");
    return;
  }
  File queue = LittleFS.open(QUEUE_PATH, FILE_READ);
  if (!queue || !queue.available()) {
    if (queue) queue.close();
    return;
  }
  const String line = queue.readStringUntil('\n');
  queue.close();
  unsigned long sequence = 0;
  unsigned long elapsedMs = 0;
  float tankA = 0;
  float tankB = 0;
  if (sscanf(line.c_str(), "%lu,%lu,%f,%f", &sequence, &elapsedMs, &tankA, &tankB) != 4) {
    Serial.println("ERROR: entrada inválida en la cola; se conserva.");
    return;
  }

  WiFiClientSecure client;
  client.setCACert(SMARTTANKS_ROOT_CA);
  HTTPClient http;
  if (!http.begin(client, String(API_BASE_URL) + "/v1/device/readings/batch")) {
    Serial.println("API: no se pudo iniciar HTTPS.");
    return;
  }
  http.addHeader("Content-Type", "application/json");
  http.addHeader("X-Device-Id", stableDeviceId);
  http.addHeader("Authorization", String("Bearer ") + SMARTTANKS_DEVICE_SECRET);
  const int statusCode = http.POST(makeReadingsPayload(sequence, elapsedMs, tankA, tankB));
  const String response = http.getString();
  http.end();
  Serial.printf("API: HTTP %d\n", statusCode);
  if (!response.isEmpty()) Serial.println(response);
  if (statusCode == 202 && popFirstQueuedBatch()) {
    Serial.printf("API confirmó la secuencia %lu; eliminada de la cola.\n", sequence);
  }
}

void setup() {
  Serial.begin(115200);
  delay(500);

  stableDeviceId = deviceIdFromEfuse();
  bootSessionId = stableDeviceId + "-" + String(static_cast<uint32_t>(esp_random()), HEX);

  preferences.begin(PREF_NAMESPACE, false);
  savedSsid = preferences.getString(PREF_WIFI_SSID, "");
  savedPassword = preferences.getString(PREF_WIFI_PASSWORD, "");
  if (!LittleFS.begin(true)) Serial.println("ERROR: LittleFS no pudo iniciar.");

  WiFi.mode(WIFI_AP_STA);
  WiFi.setAutoReconnect(true);
  WiFi.persistent(false);

  accessPointName = String(AP_PREFIX) + deviceSuffix();
  accessPointPassword = "st-" + stableDeviceId.substring(stableDeviceId.length() - 8);

  const IPAddress portalIp(192, 168, 4, 1);
  const IPAddress subnet(255, 255, 255, 0);
  WiFi.softAPConfig(portalIp, portalIp, subnet);

  if (!WiFi.softAP(accessPointName.c_str(), accessPointPassword.c_str())) {
    Serial.println("ERROR: no se pudo crear la red temporal.");
  }

  dnsServer.start(DNS_PORT, "*", portalIp);

  Serial.println();
  Serial.println("=== SmartTank provisioning ===");
  Serial.print("Red temporal: ");
  Serial.println(accessPointName);
  Serial.print("Clave temporal: ");
  Serial.println(accessPointPassword);
  Serial.print("Portal: http://");
  Serial.println(WiFi.softAPIP());
  Serial.print("Device ID: ");
  Serial.println(stableDeviceId);

  server.on("/", HTTP_GET, handleRoot);
  server.on("/wifi", HTTP_POST, handleSaveWifi);
  server.on("/wifi/reset", HTTP_POST, handleResetWifi);
  server.on("/status", HTTP_GET, handleStatus);
  server.onNotFound([]() {
    server.sendHeader("Location", "http://192.168.4.1/", true);
    server.send(302, "text/plain", "");
  });
  server.begin();

  attemptWifiConnection();
}

void loop() {
  dnsServer.processNextRequest();
  server.handleClient();

  const uint32_t now = millis();
  if (now - lastReadingAt >= READING_INTERVAL_MS) {
    lastReadingAt = now;
    appendMockBatch();
  }
  if (now - lastSyncAt >= SYNC_INTERVAL_MS) {
    lastSyncAt = now;
    syncFirstQueuedBatch();
  }
}
