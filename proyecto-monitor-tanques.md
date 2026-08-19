# Proyecto: monitor inteligente de tanques y hub doméstico

## Objetivo

Construir un sistema escalable para dos tanques de agua que:

- Mida nivel, presión, porcentaje y litros en tiempo casi real.
- Envíe datos por Wi-Fi a una API hospedada en Internet.
- Mantenga histórico para gráficas, consumo mensual, duración de recargas y alertas.
- Siga midiendo cuando se caiga Internet y sincronice las lecturas pendientes cuando vuelva.
- Detecte huecos de comunicación y reinicios para estimar cortes de luz o Internet.
- Sirva como primera pieza de un futuro panel doméstico: luces, energía, automatizaciones y otros sensores.

## Arquitectura acordada

```text
Tanque 1 ─ manguera ─ módulo de presión 1 ┐
                                            ├─ ESP32 ─ Wi‑Fi / HTTPS ─ API hospedada
Tanque 2 ─ manguera ─ módulo de presión 2 ┘                         │
                                                                      ├─ Firebase / base de datos
                                                                      └─ Panel Ionic en tablet y teléfono
```

El ESP32 es un dispositivo de campo: lee sensores, calcula litros, guarda una cola temporal si no hay red y llama al API. La tablet no se comunica directamente con el ESP32; consulta el front/API hospedado.

No hace falta Raspberry Pi ni mini-PC para la primera versión si el backend estará hospedado. Más adelante se puede incorporar un hub local para automatizaciones y dispositivos que deban funcionar aunque no haya Internet.

## Hardware de la primera versión

| Cantidad | Componente | Función |
|---:|---|---|
| 1 | ESP32 DevKit Wi-Fi/Bluetooth | Controlador, Wi-Fi y lógica local. La antena impresa suele bastar; usar caja plástica, no metálica. |
| 2 | Módulo de presión MPS20N0040D con TM7711 | Mide presión de aire de la manguera para inferir altura de agua. |
| 2 | Manguera de 2,5 mm | Desde cada módulo hasta casi el fondo de su tanque. |
| 1 | Cargador USB de 5 V / 2 A o mejor | Alimenta el ESP32 y módulos a bajo voltaje. Nunca conectar 110/220 V a los sensores. |
| 1 | Cable USB para ESP32 | Alimentación y programación inicial. |
| 1 | Kit de cables Dupont hembra-hembra | Conexiones temporales entre placas. |
| 1 | Caja impresa en 3D | Protección de ESP32 y módulos. PETG es preferible a PLA cerca de humedad/calor. |
| Opcional | Protoboard | Pruebas sin soldar. |
| Opcional | Multímetro | Verificar voltaje, continuidad y fallos. |
| Opcional | Flotadores de nivel | Respaldo de seguridad: bajo, lleno o rebose. |

### Módulo de presión seleccionado

Datos recibidos del módulo visto:

```text
Sensor/conversor: TM7711
Rango de presión: 0 a 40 kPa (0 a 5,8 psi)
Alimentación: 3,3 a 5 V
ADC: 24 bits
Diámetro de manguera: 2,5 mm
Pines: VCC, GND, OUT, SCK
```

Es importante comprar el **módulo rojo completo**, no solo el chip negro MPS20N0040D suelto. El módulo incluye la electrónica que convierte la señal del sensor a lectura digital.

Antes de comprar, confirmar con el vendedor que trae pines macho instalados o solicitar que los suelden. Si no tiene pines, se necesita una tira de pines macho de 2,54 mm y cautín/estaño, o que la tienda haga la soldadura.

## Cómo mide el agua el sensor de presión

El módulo no se sumerge. El sensor se mantiene seco dentro de la caja. Una manguera sellada baja desde el módulo hasta casi el fondo del tanque.

```text
Módulo de presión, seco
         │
         │ manguera sellada
         │
         ▼
  extremo cerca del fondo del tanque
```

El agua comprime el aire dentro de la manguera; esa presión llega al módulo. A mayor altura de agua, mayor presión.

```text
1 m de agua ≈ 9,8 kPa
2 m de agua ≈ 19,6 kPa
40 kPa ≈ 4 m de agua (límite teórico del módulo)
```

Por tanto, un tanque de 2 m usaría aproximadamente 19,6 kPa, dentro del rango anunciado de 0–40 kPa.

### Dimensiones y litros

Si un tanque es cilíndrico y sus medidas internas son exactamente:

```text
alto: 2,00 m
diámetro: 0,51 m
```

su capacidad aproximada es:

```text
π × (0,255 m)² × 2 m = 0,408 m³ ≈ 408 L
```

No sería un tanque de 1.000 L. Verificar medidas internas reales antes de programar la capacidad. Para un tanque cilíndrico:

```text
altura_agua_m = presión_kPa / 9,80665
litros = π × radio_m² × altura_agua_m × 1000
```

La implementación final debe calibrarse con dos puntos reales:

1. Tanque vacío: guardar lectura de presión como 0 %.
2. Tanque lleno: guardar lectura de presión como 100 %.

Así se compensan tolerancias del sensor, manguera, instalación y geometría real.

## Lectura y frecuencia

El TM7711 admite 10 o 40 muestras por segundo. Una muestra tarda aproximadamente 25–100 ms. Para reducir ruido:

1. Tomar 10–20 muestras rápidas por sensor.
2. Calcular promedio o mediana.
3. Convertir a presión, altura, porcentaje y litros.
4. Guardar/enviar un único registro estable.

El ciclo de ambos tanques tarda pocos segundos. Registrar cada **30 segundos** es viable y da una sensación de tiempo real. Cada minuto también sería suficiente para consumo de agua.

## Conexión inicial

Usar 3,3 V para evitar señales de 5 V hacia el ESP32. La asignación de GPIO puede variar, pero una propuesta inicial es:

```text
Módulo 1                  ESP32
VCC  ------------------>  3V3
GND  ------------------>  GND
OUT  ------------------>  GPIO 18
SCK  ------------------>  GPIO 19

Módulo 2                  ESP32
VCC  ------------------>  3V3
GND  ------------------>  GND
OUT  ------------------>  GPIO 21
SCK  ------------------>  GPIO 22
```

Confirmar el pinout impreso en los módulos físicos antes de energizarlos. Los cables Dupont hembra-hembra se enchufan sobre pines macho. El ESP32 y los módulos deben quedar dentro de la caja, cerca entre sí; solo las mangueras recorren la distancia hasta los tanques.

## Encendido, apagones y autonomía

El ESP32 arranca automáticamente cuando vuelve la corriente:

```text
Se va la luz → ESP32 se apaga.
Vuelve la luz → el cargador USB entrega 5 V → ESP32 arranca solo.
```

El firmware debe ejecutar al arrancar:

1. Inicializar sensores y cola local.
2. Intentar conectarse a Wi-Fi.
3. Reintentar con espera progresiva si no hay Wi-Fi/Internet.
4. Medir normalmente siempre que haya corriente.
5. Sincronizar pendientes al API cuando vuelva la conexión.
6. Enviar un evento `boot_started` con causa de reinicio si está disponible.

Usar un cargador de buena calidad y activar el watchdog del ESP32 para que se reinicie si se bloquea.

### Cola local sin microSD ni RTC

Por ahora no se usará RTC ni microSD. Solo se guardan las lecturas que el API no haya confirmado.

```text
Lectura cada 30 s o 1 min
     ↓
¿API confirma recepción?
  Sí → no se guarda localmente
  No → se guarda en la flash interna en una cola FIFO
     ↓
Cuando vuelve Internet → enviar pendientes en orden → borrar solo tras confirmación
```

Para horas sin Internet, la flash interna es suficiente. Escribir solo durante desconexiones minimiza el desgaste. La cola debe ser persistente para sobrevivir reinicios, con límite de tamaño y política FIFO.

Cada lectura pendiente debe guardar:

```text
sequence              número incremental
bootSessionId         identificador de arranque
elapsedMs             milisegundos desde el arranque
sensorId + medición   presión, altura, porcentaje y litros de cada sensor
timestamp             fecha/hora si ya era conocida; nula si no
timestampQuality      verified | estimated | pending
```

### Reconstrucción de tiempo sin RTC

Si se cae Internet pero el ESP32 queda encendido, mantiene una hora aproximada y puede registrar normalmente. Si se va luz e Internet juntos, el ESP32 no sabe la hora al volver hasta recuperar red.

Estrategia acordada:

1. Tras encender sin Internet, tomar lecturas normales cada intervalo y guardar `elapsedMs`.
2. Cuando vuelva Internet, sincronizar reloj por NTP y tomar una lectura ancla con hora real.
3. Reconstruir las lecturas previas hacia atrás usando los intervalos reales/`elapsedMs`.
4. Enviar esos registros con `timestampQuality: estimated`.
5. Las lecturas posteriores tienen `timestampQuality: verified`.

No se puede medir durante un apagón porque el ESP32 está apagado. El backend puede inferir un posible corte por el hueco entre el último reporte y el siguiente evento de arranque. Esto permite gráficas mensuales de frecuencia y duración estimada de cortes, diferenciando de las pérdidas de Internet con eventos/heartbeats.

## Arquitectura cloud propuesta

```text
ESP32 ── HTTPS POST ──> API / Cloud Function
                              │
                              ├─ valida dispositivo
                              ├─ guarda en Firestore
                              └─ calcula/produce eventos

Ionic (tablet/teléfono) ── HTTPS/Firebase Auth ──> API y datos autorizados
```

Stack inicial propuesto:

- **Firebase Auth**: cuentas de usuarios.
- **Cloud Functions / API HTTPS**: recepción segura de lecturas y reglas de negocio.
- **Cloud Firestore**: casas, dispositivos, tanques, lecturas y eventos.
- **Firebase Hosting**: publicar el panel Ionic/PWA.
- **Ionic**: interfaz en tablet Android y teléfono.

El ESP32 no debe escribir directamente en Firestore ni incluir credenciales administrativas de Firebase. Solo llama al API por HTTPS. El API valida y usa permisos de servidor para guardar datos.

## Modelo de datos

```text
users/{userId}
homes/{homeId}
homes/{homeId}/members/{userId}
homes/{homeId}/tanks/{tankId}
devices/{deviceId}
readings/{readingId}
deviceEvents/{eventId}
```

### Usuario y casa

```text
users
  id, displayName, email, createdAt

homes
  id, name, timezone, ownerUserId, createdAt

home members
  userId, role: owner | admin | viewer
```

Una casa puede tener varios miembros. El ESP32 pertenece a una casa; no directamente a un usuario. Si cambia el dueño de la casa, se actualiza el propietario/miembros de la casa, sin reconfigurar el ESP32.

### Dispositivo

```json
{
  "id": "smarttank-84f703123456",
  "serialNumber": "CASA-ESP-001",
  "homeId": "home_01J...",
  "status": "active",
  "firmwareVersion": "1.0.0",
  "deviceSecretHash": "...",
  "setupPinHash": "...",
  "sensorMode": "discovery"
}
```

El dispositivo tiene una sola `homeId` activa. Si se mueve a otra casa, se realiza una transferencia explícita y las lecturas antiguas permanecen ligadas a la casa original.

### Tanque

```json
{
  "id": "smarttank-84f703123456:pressure-a",
  "homeId": "home_01J...",
  "deviceId": "smarttank-84f703123456",
  "sensorId": "pressure-a",
  "name": "Tanque pressure-a",
  "configurationStatus": "pending",
  "discoveredAt": "2026-08-18T15:20:03Z",
  "status": "active"
}
```

### Lectura

```json
{
  "id": "smarttank-84f703123456:18422:pressure-a",
  "deviceId": "smarttank-84f703123456",
  "sensorId": "pressure-a",
  "homeId": "home_01J...",
  "tankId": "smarttank-84f703123456:pressure-a",
  "sequence": 18422,
  "observedAt": "2026-08-18T15:20:00Z",
  "receivedAt": "2026-08-18T15:20:03Z",
  "timestampQuality": "verified",
  "pressureKpa": 13.4,
  "waterHeightCm": 136.6,
  "percentage": 68.3,
  "liters": 276,
  "wifiRssi": -62
}
```

`observedAt` es el momento de medida; `receivedAt` es el momento de llegada al servidor. Para lecturas reconstruidas usar `timestampQuality: estimated`.

### Eventos

Ejemplos:

```text
boot_started
wifi_disconnected
wifi_reconnected
internet_disconnected
sync_started
sync_completed
time_reconstructed
sensor_error
low_water_alert
```

El backend puede derivar `possible_power_outage` y `possible_internet_outage` a partir de huecos, heartbeats y eventos, pero sin batería/RTC no puede afirmar al 100 % el instante exacto de un apagón.

## Registro y seguridad del dispositivo

El flujo se simplifica: no se requiere botón físico.

1. Cada ESP32 se prepara con un `deviceId` único, un PIN único inicial y una credencial secreta propia.
2. El usuario crea su cuenta y una casa.
3. En la app selecciona **Agregar dispositivo**.
4. Escribe o escanea el `deviceId` e introduce el PIN.
5. El API verifica el PIN y que el dispositivo no esté asignado.
6. El backend vincula `deviceId → homeId`.
7. El ESP32 continúa enviando datos sin conocer el usuario ni la casa.
8. La primera lectura de cada `sensorId` crea el tanque correspondiente en esa casa.

El ESP32 usa `deviceId` + su credencial privada para cada llamada al API. El usuario nunca necesita conocer esa credencial.

Medidas mínimas:

- HTTPS obligatorio.
- Un secreto distinto por ESP32; nunca una clave global compartida.
- Guardar PIN y secreto como hashes/cifrados en el backend; no en texto plano.
- Rate limiting de intentos de PIN.
- Lecturas idempotentes usando `deviceId + sequence + sensorId` para tolerar reintentos sin duplicar datos.
- Revocación y rotación de credenciales de dispositivo.
- Transferencia de dispositivo: solo el dueño/admin de la casa actual puede liberar/generar un nuevo PIN de transferencia.
- Registrar auditoría de vinculación, desvinculación y cambios de calibración.
- El API exige un `sensorId` lógico estable y descubre un tanque por cada sensor autenticado del dispositivo.

## Endpoints REST iniciales

### Para ESP32

```text
POST /v1/device/readings/batch
POST /v1/device/events
GET  /v1/device/config
```

Ejemplo de lote:

```json
{
  "deviceId": "smarttank-84f703123456",
  "readings": [
    {
      "sequence": 18422,
      "sensorId": "pressure-a",
      "observedAt": "2026-08-18T15:20:00Z",
      "timestampQuality": "verified",
      "pressureKpa": 13.4,
      "liters": 276
    }
  ]
}
```

La respuesta debe indicar qué combinaciones `sequence + sensorId` fueron aceptadas. El ESP32 borra de la cola únicamente esas lecturas confirmadas.

### Para la aplicación

```text
POST /v1/homes
POST /v1/homes/{homeId}/devices/claim
PATCH /v1/homes/{homeId}/tanks/{tankId}
GET  /v1/homes/{homeId}/dashboard
GET  /v1/tanks/{tankId}/readings?from=...&to=...
GET  /v1/tanks/{tankId}/statistics?period=month
POST /v1/devices/{deviceId}/transfer-pin
```

## Panel Ionic inicial

La primera pantalla debería mostrar:

- Un tanque por cada sensor descubierto: presión y los valores de litros, porcentaje o nivel que estén disponibles.
- Nombre personalizable sin cambiar la identidad técnica `deviceId + sensorId`.
- Estado de conectividad: dispositivo online/offline y última comunicación.
- Alertas: nivel bajo, lectura desactualizada, sensor con error.
- Gráfica de consumo por día, semana y mes.
- Última recarga: momento, litros iniciales y duración estimada.
- Historial de eventos de red y posibles cortes eléctricos.

Más adelante se pueden sumar luces, interruptores inteligentes, consumo eléctrico, escenas domésticas y otros dispositivos. Para luces de varias marcas puede ser útil incorporar Home Assistant/hub local como una capa futura; el panel Ionic y la API cloud pueden mantenerse.

## Decisiones pendientes antes de construir

1. Medir correctamente dimensiones internas y capacidad real de ambos tanques.
2. Comprar un módulo de prueba y verificar su lectura con una columna de agua real.
3. Confirmar pines macho/headers incluidos en los módulos.
4. Elegir intervalo inicial: 30 segundos recomendado para visualización casi en tiempo real.
5. Definir si se usa Firebase Cloud Functions + Firestore desde el primer día.
6. Definir formato final de credencial del ESP32 y proceso de aprovisionamiento de `deviceId`, PIN y secreto.
7. Diseñar la carcasa 3D con salidas selladas para dos mangueras y cable USB.

## Próximo orden recomendado

1. Validar un módulo de presión con un tanque real.
2. Conectar un módulo al ESP32 y leer valores crudos.
3. Hacer calibración vacío/lleno.
4. Implementar medición estable y cálculo de litros.
5. Crear API de prueba y envío HTTPS.
6. Implementar cola persistente de pendientes y sincronización por lote.
7. Crear Firebase/Auth/modelo de datos/claim de dispositivo.
8. Construir el panel Ionic.
9. Instalar de forma definitiva en caja impresa en 3D.
