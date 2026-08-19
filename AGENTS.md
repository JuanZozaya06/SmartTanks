# AGENTS.md — SmartTanks

Este archivo define cómo continuar SmartTanks sin contradecir las decisiones ya tomadas. Aplica a todo el repositorio.

## Objetivo del producto

SmartTanks monitorea inicialmente dos tanques de agua con un ESP32 y dos sensores de presión. Debe mostrar nivel, porcentaje, litros, histórico, consumo, alertas y estado de conectividad. El dispositivo debe seguir midiendo sin Internet, conservar una cola local y sincronizarla al recuperar conexión.

La solución debe poder crecer después hacia un panel doméstico con energía, luces, automatizaciones y otros sensores, pero no se debe ampliar el alcance de la primera versión sin una petición explícita.

## Fuentes de verdad

Antes de hacer cambios relevantes, revisar en este orden:

1. `AGENTS.md`: reglas de implementación y decisiones vigentes.
2. `proyecto-monitor-tanques.md`: requisitos de producto, hardware y comportamiento offline.
3. `docs/architecture.md`: arquitectura técnica, contratos y decisiones pendientes.
4. Código y pruebas: comportamiento realmente implementado.
5. `README.md`: instrucciones operativas para el equipo.

Si dos fuentes se contradicen, no cambiar silenciosamente la arquitectura. Explicar la diferencia y actualizar juntas las fuentes afectadas cuando la decisión esté confirmada.

## Arquitectura decidida

```text
ESP32 ── HTTPS ──► Cloud Function Python ──► Cloud Firestore
                          │                         │
                          └── Firebase Auth ◄── Angular
                                                   │
                                            GitHub Pages
```

- Proyecto Firebase: `smarttanks-830ba`.
- Región de Firestore y de la Function: `us-east1`.
- API productiva: `https://us-east1-smarttanks-830ba.cloudfunctions.net/api`.
- Base de datos: Cloud Firestore. No añadir MySQL.
- Backend: Cloud Functions for Firebase, Python 3.12, API HTTPS con Flask.
- Usuarios: Firebase Authentication.
- Frontend: Angular 22, responsive para teléfono y tablet; Ionic puede añadirse posteriormente si se decide empaquetar una aplicación móvil.
- Hosting web: GitHub Pages mediante `.github/workflows/deploy-frontend.yml`.
- Desarrollo local: Firebase Emulator Suite para Auth, Firestore y Functions.
- Plan Firebase: Blaze, necesario para desplegar Functions. Mantener límites de instancias y vigilar consumo.

No introducir Railway, un servidor permanente, Raspberry Pi o comunicación directa tablet–ESP32 salvo que se apruebe una nueva decisión arquitectónica.

## Límites de seguridad

- El ESP32 nunca escribe directamente en Firestore. Solo consume la API HTTPS.
- El navegador no escribe directamente en Firestore. Las reglas permiten lecturas autorizadas; toda escritura pasa por la API.
- Cada ESP32 usa un `deviceId` y un secreto único. El secreto viaja como `Authorization: Bearer ...`; el ID también se envía en `X-Device-Id`.
- Guardar en Firestore únicamente `deviceSecretHash`, nunca el secreto en texto plano.
- Los usuarios de la aplicación usan tokens de Firebase Auth. Verificar esos tokens en rutas de usuario mediante `require_user`.
- Nunca incluir credenciales administrativas, cuentas de servicio, secretos de dispositivo o archivos `.env` en Git.
- La configuración pública del SDK web de Firebase en `frontend/public/config.js` no es una credencial administrativa; aun así, la seguridad depende de Auth, reglas, validación de API y posteriormente App Check.
- Mantener CORS limitado a `ALLOWED_ORIGINS`. No usar `*` en producción.
- Validar todos los cuerpos externos con Pydantic y mantener `extra="forbid"`.
- Usar HTTPS, comparación constante de hashes, rate limiting para PIN/claim y auditoría para operaciones sensibles.

## Modelo Firestore y contratos

Colecciones acordadas:

```text
users/{userId}
homes/{homeId}
homes/{homeId}/members/{userId}
homes/{homeId}/tanks/{tankId}
devices/{deviceId}
readings/{deviceId}:{sequence}:{channel}
deviceEvents/{deviceId}:{bootSessionId}:{sequence}:{eventType}
```

Reglas que deben preservarse:

- El dispositivo pertenece a una casa (`homeId`), no a una persona.
- Cada unidad se preaprovisiona antes de llegar al usuario con `deviceId`, PIN de claim y secreto individual. Firestore conserva únicamente los hashes del PIN y del secreto, con estado inicial `unclaimed`.
- El `deviceId` público usa la MAC completa: `smarttank-<12 hex>`. No usar solo los últimos ocho hexadecimales como identidad definitiva.
- El usuario final no crea credenciales: reclama una unidad existente enviando `deviceId + setupPin + label`; la API asigna `homeId`, canales y estado `active`.
- Una casa puede tener miembros con roles `owner`, `admin` o `viewer`.
- Los canales del dispositivo determinan los tanques para los que puede publicar.
- Las lecturas son idempotentes. El ID incluye `deviceId`, `sequence` y `channel`; un reintento devuelve `duplicate` y cuenta como confirmado sin sobrescribir el original.
- La API actualiza `homes/{homeId}/tanks/{tankId}.latestReading` en el mismo batch que crea el histórico. Angular escucha ese documento con `onSnapshot()`; no debe hacer polling del estado actual.
- Distinguir siempre `observedAt` (momento medido) de `receivedAt` (momento recibido por el servidor).
- `timestampQuality` solo puede ser `verified`, `estimated` o `pending`.
- Conservar `bootSessionId` y `elapsedMs` para reconstruir tiempo y analizar reinicios.
- No afirmar que hubo un apagón solo por un hueco. Los eventos derivados deben llamarse `possible_power_outage` o `possible_internet_outage` hasta disponer de evidencia suficiente.

Endpoints de dispositivo vigentes:

```text
GET  /v1/health
POST /v1/device/readings/batch
POST /v1/device/events
GET  /v1/device/config
```

Endpoints de usuario vigentes:

```text
GET  /v1/me/context
POST /v1/homes
GET  /v1/homes/{homeId}/devices
POST /v1/homes/{homeId}/devices/claim
```

El registro, inicio y cierre de sesión se realizan con Firebase Auth en el navegador. `POST /v1/homes` crea usuario de aplicación, casa, membresía `owner` y tanques en un batch; el navegador nunca escribe estos documentos directamente.

Rutas de usuario pendientes:

```text
GET  /v1/homes/{homeId}/dashboard
GET  /v1/tanks/{tankId}/readings?from=...&to=...
GET  /v1/tanks/{tankId}/statistics?period=month
POST /v1/devices/{deviceId}/transfer-pin
```

No exponer una ruta de provisión al usuario final. El PIN usa PBKDF2 con sal y el claim se bloquea tras cinco fallos. Un posible auto-registro iniciado por el ESP32 sigue pendiente: no crear registros anónimos ni confiar únicamente en la MAC, que es pública y falsificable. No modificar el firmware salvo petición explícita.

Cuando cambie un contrato, actualizar el esquema, pruebas, `docs/api-examples.http` y documentación en el mismo cambio.

## Reglas para el backend

- `backend/main.py` debe seguir siendo el punto de entrada mínimo que expone una sola Function HTTPS llamada `api`.
- La API pública se versiona bajo `/v1`.
- Mantener la Function en `us-east1`, Python 3.12, 256 MB, timeout de 60 segundos y `max_instances=3`, salvo que exista una razón medida para cambiarlo.
- No crear el cliente de Firestore durante la importación de módulos. Usar `get_firestore_client()` dentro de la ejecución de las rutas. Firebase importa `main.py` sin credenciales locales durante el análisis del despliegue.
- `get_firestore_client()` usa credenciales anónimas únicamente cuando existe `FIRESTORE_EMULATOR_HOST`; en producción usa Firebase Admin/Application Default Credentials.
- Usar fechas conscientes de zona horaria y UTC en el servidor.
- Mantener respuestas de error consistentes: `{ "error": { "message": ..., "details": ... } }`.
- Añadir pruebas para validación, autenticación, autorización, idempotencia y errores antes de ampliar rutas.

## Reglas para el frontend

- Mantener Angular con componentes standalone y estilos SCSS.
- En todos los textos visibles para el usuario, llamar al equipo **SmartTank**; reservar **ESP32** para documentación técnica, código y diagnóstico interno.
- Obtener Firebase y `apiBaseUrl` mediante `frontend/public/config.js` y `runtime-config.ts`; no dispersar URLs o configuración por componentes.
- Respetar `runtimeConfig.useEmulators`: con `true`, Auth, Firestore y API apuntan a Emulator Suite; con `false`, incluso localhost usa producción. No cambiar este indicador silenciosamente ni ejecutar pruebas destructivas contra producción.
- No usar datos demostrativos. Mostrar acceso sin sesión, onboarding sin casa y datos reales con contexto válido.
- Iniciar listeners de tanques solo con usuario autenticado y casa devuelta por `/v1/me/context`.
- Toda operación de escritura y toda regla de negocio pasa por `ApiService` hacia el backend.
- Las lecturas directas de Firestore, cuando se implementen, deben respetar membresía de casa y ventanas de consulta limitadas.
- Diseñar primero para tablet y teléfono: dos tanques, última lectura, estado online/offline, alertas y gráficas por día/semana/mes.
- Mantener compatibilidad con GitHub Pages: respetar el `base-href` del repositorio y la copia de `index.html` a `404.html` realizada por el workflow.
- No agregar Ionic hasta que se decida si se requiere empaquetado móvil; Angular web es la base vigente.

## Reglas para el firmware

- Los módulos de presión permanecen secos; solo la manguera llega al tanque.
- Usar 3,3 V y confirmar el pinout físico antes de energizar.
- Muestrear varias veces y filtrar antes de generar una lectura estable.
- Intervalo inicial recomendado: 30 segundos; 60 segundos sigue siendo una decisión posible.
- La medición continúa sin Internet mientras exista energía.
- Guardar en flash solo las lecturas no confirmadas, en una cola FIFO persistente con límite de tamaño.
- Borrar de la cola únicamente las combinaciones `sequence + channel` confirmadas por la API.
- Sin RTC, conservar `elapsedMs`; reconstruir horas tras sincronizar NTP y marcar esas lecturas como `estimated`.
- Enviar eventos de arranque, Wi-Fi, Internet, sincronización y sensores. Activar watchdog y reintento con espera progresiva.
- Nunca incrustar claves administrativas de Firebase en el firmware.

## Entorno local en Windows

Trabajar desde PowerShell y desde la raíz del repositorio salvo que el comando indique lo contrario.

Crear el entorno de Python directamente en su ruta definitiva. Los lanzadores de Windows guardan rutas absolutas: no crear el entorno con otro nombre para luego renombrarlo.

```powershell
py -3.12 -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements-dev.txt

Set-Location frontend
npm ci
Set-Location ..
```

Usar una versión de Node compatible con `frontend/package.json` y verificarla con `node --version`. No modificar el rango `engines` solo para silenciar una advertencia.

## Validación obligatoria

Ejecutar las verificaciones relacionadas con cada cambio. Antes de declarar lista una modificación que afecte varias capas, ejecutar como mínimo:

```powershell
Push-Location backend
.\venv\Scripts\python -m ruff check .
.\venv\Scripts\python -m pytest -q
Pop-Location

Push-Location frontend
npm test -- --watch=false
npm run build
Pop-Location
```

Para cambios de Functions o Firestore, comprobar además el emulador:

```powershell
npx firebase-tools emulators:start
```

Verificar al menos:

```text
http://127.0.0.1:5001/smarttanks-830ba/us-east1/api/v1/health
```

La respuesta esperada es `{"service":"smart-tanks-api","status":"ok"}`. Detener los emuladores al terminar las pruebas.

## Despliegues y cambios externos

- No desplegar, hacer push, crear PR, habilitar APIs, cambiar facturación ni modificar datos de producción salvo petición explícita del usuario.
- Firestore y Functions se despliegan desde la raíz:

```powershell
npx firebase-tools deploy --only firestore
npx firebase-tools deploy --only functions
```

- Tras desplegar la Function, actualizar `apiBaseUrl` en `frontend/public/config.js` con la URL pública real y validar CORS.
- El frontend se publica al hacer push a `main` mediante GitHub Actions, por lo que ese push también es un despliegue.
- No considerar `DEP0190` de Node como la causa de un fallo si el registro contiene una excepción posterior; diagnosticar la última excepción real.

## Costos y volumen

Dos tanques cada 30 segundos generan hasta 5.760 documentos históricos y 5.760 actualizaciones de estado: unas 11.520 escrituras diarias antes de eventos. Mantener consultas acotadas, usar resúmenes para gráficas extensas y vigilar las cuotas. No añadir listeners o consultas sin límite. Las alertas de presupuesto avisan, pero no detienen automáticamente el gasto.

## Decisiones aún pendientes

No inventar valores para estos puntos; usar una configuración clara o solicitar la decisión cuando bloquee el trabajo:

- Dimensiones internas, capacidad y calibración vacío/lleno de ambos tanques.
- Intervalo definitivo de 30 o 60 segundos.
- Mecanismo operativo para precargar unidades y para rotar o transferir el secreto del ESP32.
- Aprobar o descartar el auto-registro del ESP32 y, si se aprueba, definir una credencial segura de bootstrap.
- Angular web puro o Ionic Angular para una aplicación móvil instalable.
- Agregados diarios/mensuales, retención y posible TTL de lecturas crudas.
- Diseño físico final de la carcasa y validación del sensor con columna de agua real.

## Criterio de terminado

Un cambio está terminado cuando:

1. Respeta la frontera ESP32 → API → Firestore y las reglas de autorización.
2. Incluye o actualiza pruebas del comportamiento modificado.
3. Pasa las validaciones pertinentes sin ocultar errores.
4. No contiene secretos ni datos de producción innecesarios.
5. Actualiza contratos y documentación afectados.
6. Indica claramente cualquier decisión pendiente, riesgo de costo o paso externo que todavía deba realizar el usuario.
