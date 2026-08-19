# Arquitectura técnica

Este diseño traduce los requisitos de `proyecto-monitor-tanques.md` a Firebase sin perder la frontera de seguridad que representa la API.

## Componentes

| Componente | Tecnología | Responsabilidad |
|---|---|---|
| Dispositivo | ESP32 | Muestreo, cálculo, cola flash, NTP y sincronización |
| API | Cloud Functions, Python | Autenticar, validar, deduplicar y escribir |
| Datos | Cloud Firestore | Casas, tanques, dispositivos, lecturas y eventos |
| Usuarios | Firebase Auth | Inicio de sesión y tokens del panel |
| Panel | Angular | Estado, gráficas, alertas, configuración y claim |
| Web | GitHub Pages | Archivos estáticos del panel |

## Colecciones Firestore

```text
users/{userId}
homes/{homeId}
homes/{homeId}/members/{userId}
homes/{homeId}/tanks/{tankId}
devices/{deviceId}
readings/{deviceId}:{sequence}:{sensorId}
deviceEvents/{deviceId}:{bootSessionId}:{sequence}:{eventType}
```

El identificador de lectura incluye `sensorId` porque un mismo ciclo/`sequence` puede producir datos de varios sensores. Cada ESP32 tiene un solo `deviceId`; sus sensores usan identificadores lógicos estables como `pressure-a`. Un reintento devuelve `duplicate` y se considera confirmado, pero no sobrescribe la primera lectura guardada.

`POST /v1/homes` no crea tanques. La primera lectura autenticada de cada combinación `deviceId + sensorId` crea `homes/{homeId}/tanks/{deviceId}:{sensorId}` con `configurationStatus: pending`, nombre referencial y `latestReading`. La API crea el histórico y actualiza el tanque dentro del mismo batch. Angular escucha la colección completa con `onSnapshot()`, por lo que descubre sensores nuevos sin recargar ni hacer polling.

Cada tanque cilíndrico se configura desde el panel con `heightCm`, `diameterCm` y `fullPressureKpa`. La capacidad y los valores derivados se calculan en la API:

```text
capacityLiters = π × (diameterCm / 2)² × heightCm / 1000
percentage = clamp(pressureKpa / fullPressureKpa × 100, 0, 100)
waterHeightCm = heightCm × percentage / 100
liters = capacityLiters × percentage / 100
```

La primera versión asume `0 kPa = tanque vacío`. Para establecer el punto de 100 %, el usuario llena físicamente el tanque y captura desde Angular su presión actual. El dispositivo solo aporta la presión cruda; la API elimina cualquier porcentaje, altura o litraje enviado por él y los vuelve a calcular. Hasta completar la configuración, se conserva y muestra la presión, pero los valores derivados permanecen ausentes. Cambiar la configuración recalcula `latestReading`; no reescribe los documentos históricos anteriores.

```text
API crea readings/{id} ─┐
                        ├─ batch atómico ─► homes/{homeId}/tanks/{tankId}.latestReading
API confirma secuencia ─┘                                      │
                                                               └─ onSnapshot() ─► Angular
```

El listener solo se inicia cuando existe un usuario autenticado y `/v1/me/context` confirma su casa y membresía. Las reglas permiten la lectura del tanque a miembros, pero todas las escrituras continúan pasando por la API.

## Histórico de nivel

`GET /v1/tanks/{tankId}/readings` verifica la sesión, la casa activa y la membresía antes de consultar `readings`. Acepta `period=day|week|month`, correspondientes a las últimas 24 horas, 7 días o 30 días. También acepta `from` y `to` juntos como fechas ISO 8601 con zona horaria, con un máximo de 31 días.

La respuesta agrupa las lecturas en intervalos de 5 minutos para día, 30 minutos para semana y 2 horas para mes. Cada punto conserva promedio, mínimo, máximo, primer y último valor, cantidad de muestras y la peor `timestampQuality` presente. El panel usa `observedAt`, corta la línea cuando existen huecos y marca como estimados los intervalos que no son completamente `verified`.

Los porcentajes y litros del histórico se recalculan desde `pressureKpa` con la configuración actual del tanque. Esto permite representar mediciones anteriores a la calibración y aplicar correcciones de calibración sin reescribir documentos históricos.

Cuando un lote nuevo llega sin `observedAt`, conserva `elapsedMs` y contiene más de un instante distinto, la API toma la lectura con mayor tiempo transcurrido como ancla en `receivedAt` y reconstruye las anteriores por diferencia de milisegundos. Esas fechas se guardan exclusivamente como `timestampQuality: estimated`. Un lote con un único instante permanece `pending`, porque podría ser una fila antigua sincronizada después de una desconexión. Para documentos antiguos que todavía tienen `observedAt: null`, la consulta histórica realiza el cálculo por `bootSessionId` sin reescribirlos. `receivedAt` no se presenta como si fuera una hora verificada; el firmware debe sincronizar NTP para producir lecturas `verified`.

La agrupación actual ocurre dentro de la petición y reduce el tamaño de la respuesta, pero todavía lee los documentos crudos de la ventana seleccionada. Antes de aumentar dispositivos o retención se deben incorporar agregados persistentes horarios/diarios para evitar releer un mes completo en cada apertura.

## Flujo de cuenta y configuración inicial

```text
registro/login con correo y contraseña
                │
                ▼
         Firebase Authentication
                │ ID token
                ▼
        GET /v1/me/context
                │
       ┌────────┴─────────┐
       │ sin casa         │ con casa
       ▼                  ▼
POST /v1/homes        dashboard + onSnapshot()
       │
       └─ crea usuario, casa y owner en un batch; tanks queda vacío
```

El frontend no guarda un `homeId` manual ni contiene lecturas ficticias. Firebase Auth conserva la sesión; al recargar, Angular obtiene un token nuevo y reconstruye el contexto desde la API.

## Flujo de lecturas

```text
medir ambos sensores
        │
        ▼
POST /v1/device/readings/batch
        │
        ├─ validar deviceId + secreto
        ├─ validar sensorId estable
        ├─ detectar documentos ya existentes
        ├─ derivar porcentaje y litros si el tanque está configurado
        └─ crear lectura y descubrir tanque si es necesario
                    │
                    ▼
      responder cada sequence + sensorId
                    │
                    ▼
 ESP32 elimina únicamente los confirmados
```

El secreto del dispositivo se envía como `Authorization: Bearer ...`; en Firestore solo se almacena su SHA-256 (`deviceSecretHash`). Cada dispositivo tiene su propio secreto. El ID también viaja en `X-Device-Id` y en el cuerpo para evitar confusiones de identidad.

## Provisión y asociación del dispositivo

```text
fabricación ─► devices/{deviceId}, status unclaimed
                │ hashes de PIN y secreto individual
                ▼
usuario final ─ deviceId + PIN + nombre referencial
                │
                ▼
POST devices/claim ─► homeId + label + status active
```

- El secreto tiene alta entropía y en Firestore solo queda su SHA-256.
- El PIN usa PBKDF2-SHA256 con sal única y 210.000 iteraciones.
- Cinco intentos incorrectos bloquean el claim.
- El claim genera un documento en `auditLogs`, inaccesible desde el navegador.
- Solo `owner` o `admin` puede asociar; cualquier miembro válido puede listar SmartTanks de su casa.
- El usuario final no genera ni ve el secreto individual del equipo.
- El `deviceId` tiene el formato `smarttank-<12 hex>` y se deriva de la eFuse/MAC de fábrica del ESP32. Es público; el secreto es la credencial.
- Se usa la MAC completa, no solo los últimos ocho hexadecimales, para reducir colisiones.
- El claim no crea tanques ni asigna canales. Los tanques aparecen solo después de mediciones reales.
- El usuario con rol `owner` o `admin` puede cambiar nombre, altura, diámetro y presión de lleno con `PATCH /v1/homes/{homeId}/tanks/{tankId}`; la identidad técnica `deviceId + sensorId` no cambia.
- El auto-registro en el primer arranque no está aprobado. Si se implementa, debe autenticar el alta mediante una credencial de bootstrap y, cuando el registro ya exista, verificar el secreto individual en vez de ignorar ciegamente la solicitud.

## Tiempo y cortes

- `observedAt`: hora de la medición; puede ser nula mientras no exista ancla NTP.
- `receivedAt`: hora del servidor, siempre presente.
- `timestampQuality`: `verified`, `estimated` o `pending`.
- `bootSessionId` + `elapsedMs`: permiten reconstruir tiempo y distinguir reinicios.
- Si el dispositivo todavía no implementa NTP, la API puede usar `receivedAt` únicamente como ancla para reconstruir por diferencia de `elapsedMs`; el resultado sigue siendo estimado.
- Los eventos no afirman por sí solos un apagón; una tarea posterior derivará `possible_power_outage` o `possible_internet_outage` a partir de huecos y reinicios.

## Cuotas y costo esperado

Dos tanques cada 30 segundos generan como máximo 5.760 documentos históricos y 5.760 actualizaciones de estado por día, antes de eventos y configuración: aproximadamente 11.520 escrituras diarias. Esto mantiene margen dentro de la cuota gratuita de 20.000 escrituras diarias, pero el intervalo o el modelo debe revisarse antes de añadir más dispositivos. Los listeners generan lecturas facturables cuando reciben cambios; las consultas históricas deben pedir ventanas limitadas o resúmenes agregados.

Cloud Functions requiere Blaze y una cuenta de facturación. Deben configurarse alertas de presupuesto; una alerta avisa, pero no detiene automáticamente el gasto. La Function limita inicialmente sus instancias a tres.

## Seguridad pendiente antes de producción

1. Definir la herramienta operativa de aprovisionamiento de fábrica.
2. Aprobar o descartar el auto-registro y su credencial de bootstrap.
3. Implementar transferencia y rotación de credenciales.
4. Añadir App Check al panel.
5. Añadir la ruta autenticada de estadísticas.
6. Incorporar validación automatizada de reglas sin ejecutar casos destructivos contra producción.
7. Configurar retención o agregación de históricos antes de crecer; TTL no entra en la cuota gratuita.

## Decisiones de producto aún abiertas

- Valores reales de altura, diámetro y presión de lleno de cada tanque; el mecanismo para guardarlos ya está definido en el panel y la API.
- Intervalo definitivo de 30 o 60 segundos.
- Herramienta de aprovisionamiento, posible bootstrap y rotación del secreto del ESP32.
- Si el panel final usa Angular puro o Ionic Angular para empaquetado móvil.
- Estrategia de agregados diarios/mensuales y retención de lecturas crudas.
