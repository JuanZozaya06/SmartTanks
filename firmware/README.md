# Firmware ESP32

## `SmartTanksProvisioning`

Sketch Arduino para la instalación inicial y la primera prueba de telemetría.

- Crea una red temporal `SmartTank-XXXX`.
- Genera una clave WPA2 única por unidad: `st-` más los últimos ocho caracteres
  del `deviceId`. En producción se imprime junto al QR de instalación; también
  aparece en el Monitor Serial durante pruebas.
- Sirve un portal local en `http://192.168.4.1`.
- Guarda SSID y contraseña Wi-Fi en `Preferences` (NVS) del ESP32.
- Intenta reconectarse a la red guardada después de cada reinicio.
- Mantiene AP y cliente Wi-Fi activos simultáneamente durante el desarrollo.
- Genera dos lecturas mock cada 30 segundos, las conserva en una cola LittleFS
  hasta recibir HTTP 202 y las envía al API HTTPS real.

## ID, PIN y secreto del dispositivo

Al iniciar, el Monitor Serial muestra un ID como `smarttank-84f703123456`.
Proviene de la eFuse/MAC de fábrica del ESP32: es único por placa y persiste
entre reinicios. Es un identificador público, no el mecanismo de seguridad.

Antes de cargar una unidad para un cliente, el proceso de fábrica/instalador
crea en Firestore `devices/{deviceId}` con estado `unclaimed`, el hash del PIN
de ocho dígitos y el hash del secreto. La etiqueta o QR de la unidad muestra al
cliente únicamente el `deviceId` y el PIN.

El firmware recibe únicamente el secreto individual, mediante:

1. Copia `SmartTanksProvisioning/arduino_secrets.h.example` como
   `SmartTanksProvisioning/arduino_secrets.h`.
2. Sustituye `SMARTTANKS_DEVICE_SECRET` por el secreto ya asignado a esa placa.
3. Sube el sketch y abre el Monitor Serial a 115200 baudios.

Ese archivo no entra a Git. El firmware **no conoce ni envía el PIN** y nunca
llama al endpoint de claim. Mientras el cliente no complete el claim desde la
web, el API responderá 401/403 a las lecturas porque el dispositivo sigue sin
`homeId` y canales A/B; la cola no se borra. Tras el claim, las mismas lecturas
pendientes se sincronizan normalmente.

## Cargarlo

1. En Arduino IDE abre `firmware/SmartTanksProvisioning/SmartTanksProvisioning.ino`.
2. Selecciona `ESP32 Dev Module` y el puerto del dispositivo, actualmente `COM5`.
3. Sube el sketch.
4. Con el teléfono, busca la red `SmartTank-XXXX` que aparezca en el Monitor Serial.
5. Conéctate con la clave temporal impresa en el Monitor Serial y abre `http://192.168.4.1`.
6. Ingresa las credenciales del Wi-Fi de la casa.

No envíes la clave Wi-Fi al API. Las llamadas al backend usan HTTPS y validan
la cadena TLS contra el certificado raíz configurado en `certificates.h`.

## Antes de producción

- Proteger las credenciales Wi-Fi en flash mediante las capacidades de seguridad del ESP32 apropiadas para el hardware final.
- Apagar o restringir el AP una vez confirmado el aprovisionamiento.
- Integrar el flujo de claim (`deviceId` + PIN) con el backend.
