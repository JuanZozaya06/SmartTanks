# SmartTanks

Monitor inteligente para dos tanques de agua basado en ESP32, una API serverless y un panel web.

## Arquitectura elegida

```text
ESP32 ── HTTPS ──► Cloud Function Python ──► Cloud Firestore
                          │                         │
                          └── Firebase Auth ◄── Angular
                                                   │
                                            GitHub Pages
```

- **Base de datos:** Cloud Firestore.
- **Servidor:** Cloud Functions for Firebase, con Python 3.12 y una API HTTPS versionada.
- **Identidad:** Firebase Authentication para las cuentas del panel.
- **Frontend:** Angular 22, adaptable a móvil/tablet y preparado para añadir componentes Ionic.
- **Hosting:** GitHub Pages mediante GitHub Actions.
- **Desarrollo local:** pruebas unitarias aisladas con dobles; el panel local usa Firebase productivo.

No se usa MySQL ni Railway en esta versión. La API es la única que escribe: el ESP32 no recibe credenciales administrativas y el navegador queda limitado por las reglas de Firestore.

## Carpetas

```text
backend/                 Cloud Function Python y pruebas
frontend/                Aplicación Angular
docs/                    Arquitectura y contratos
.github/workflows/       Despliegue del panel
firebase.json            Configuración de Functions y Firestore
firestore.rules          Autorización de datos
firestore.indexes.json   Índices requeridos por consultas
```

## Primer arranque local

Requisitos: Node.js 24.15 o posterior (también sirve 22.22.3 o posterior), Python 3.12 y Firebase CLI.

```powershell
Copy-Item .firebaserc.example .firebaserc
# Editar .firebaserc con el project ID real.

py -3.12 -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements-dev.txt

Set-Location frontend
npm install
Set-Location ..
```

```powershell
Set-Location frontend
npm start
```

El panel abre en `http://localhost:4200` y usa los servicios productivos configurados en `frontend/public/config.js`.

Mantener `useEmulators` en `false`. No ejecutar pruebas manuales destructivas desde localhost; las pruebas automatizadas aíslan sus dependencias mediante dobles.

## Despliegue

### Backend

1. Crear el proyecto en Firebase y activar Firestore y Authentication.
2. Cambiar el ID en `.firebaserc`.
3. Activar Blaze; Cloud Functions exige una cuenta de facturación aun cuando el uso quede dentro de la cuota sin costo.
4. Verificar que `ALLOWED_ORIGINS` incluya el dominio real de GitHub Pages. Este repositorio permite por defecto `https://juanzozaya06.github.io` y `http://localhost:4200`.
5. Ejecutar:

```powershell
npx firebase-tools deploy --only functions,firestore
```

Después, actualizar `frontend/public/config.js` con la URL pública de la Function.

### Frontend

Al hacer push a `main`, el workflow publica Angular en GitHub Pages. En la configuración del repositorio se debe seleccionar **GitHub Actions** como fuente de Pages.

## Estado actual

La base implementa los endpoints del dispositivo:

- `POST /v1/device/readings/batch`
- `POST /v1/device/events`
- `GET /v1/device/config`
- `GET /v1/health`

También implementa el onboarding autenticado del panel:

- Firebase Auth con correo y contraseña para registro, sesión persistente y cierre de sesión.
- `GET /v1/me/context` para recuperar usuario, casa y tanques ya descubiertos.
- `POST /v1/homes` para crear perfil, casa y membresía `owner`, sin precrear tanques.
- `POST /v1/homes/{homeId}/devices/claim` para asociar mediante `deviceId + PIN + nombre`.
- `PATCH /v1/homes/{homeId}/tanks/{tankId}` para configurar nombre, altura, diámetro y presión de lleno de un tanque descubierto.
- `GET /v1/homes/{homeId}/devices` para listar los SmartTanks asociados.
- `GET /v1/tanks/{tankId}/readings?period=day|week|month` para obtener el histórico autenticado y agregado.

La API productiva está desplegada en:

```text
https://us-east1-smarttanks-830ba.cloudfunctions.net/api
```

El panel no contiene datos demostrativos. Sin sesión muestra acceso; sin casa muestra la configuración inicial; con una casa válida muestra únicamente datos recibidos desde Firestore.

## Actualización en tiempo real

Al aceptar un lote nuevo, la API guarda el histórico en `readings`. La primera lectura de cada `sensorId` crea automáticamente `homes/{homeId}/tanks/{deviceId}:{sensorId}`; las siguientes actualizan su `latestReading`. El panel escucha la colección con Firestore `onSnapshot()`, por lo que detecta tanques nuevos sin consultar la API cada 30 segundos.

El usuario crea su cuenta desde Angular y completa únicamente el nombre de la casa y la zona horaria. La API crea la membresía y el panel obtiene el `homeId` desde `/v1/me/context`; los tanques solo aparecen después de recibir datos reales.

Cada tanque descubierto debe configurarse desde el panel con sus medidas internas y la presión observada al estar físicamente lleno. Para un cilindro, la API calcula capacidad, porcentaje, altura de agua y litros; no confía en valores derivados enviados por el SmartTank. La versión actual usa `0 kPa` como punto de vacío. Mientras falte alguna medida o la calibración de lleno, el panel muestra la presión real, pero no presenta litros ni porcentaje calculados.

El panel ofrece vistas de las últimas 24 horas, 7 días y 30 días. La API agrupa respectivamente en intervalos de 5 minutos, 30 minutos y 2 horas, recalcula el histórico con la calibración actual y conserva los huecos de medición. También admite un rango explícito `from` + `to` de hasta 31 días. Esta agrupación limita los puntos enviados al navegador; los agregados persistentes siguen pendientes antes de aumentar la cantidad de dispositivos o la retención.

Si una versión de firmware envía `observedAt: null` pero conserva `elapsedMs` y `bootSessionId`, la API puede reconstruir una fecha estimada cuando dispone de varios instantes del mismo lote o sesión. Una fila antigua aislada permanece pendiente para no fecharla incorrectamente como si acabara de medirse. El panel distingue estas muestras; solo una hora sincronizada por NTP puede marcarse como `verified`.

Antes de usar el registro, habilitar el proveedor **Correo electrónico/contraseña** en Firebase Authentication.

## Asociación de un SmartTank

Cada equipo debe existir previamente en `devices/{deviceId}` con estado `unclaimed`, un PIN de claim y un secreto individual. Firestore guarda solamente los hashes del PIN y del secreto. El `deviceId` usa el formato `smarttank-<MAC completa de 12 hex>`.

Desde **Agregar SmartTank**, el usuario final ingresa el ID y PIN impresos en el equipo, además de un nombre referencial. Si coinciden, la API asigna el equipo a la casa, pero no crea tanques ni asigna canales. Cada lectura incluye un `sensorId` estable; la API descubre un tanque por sensor y el usuario puede cambiar su nombre desde el panel. No existe una ruta web para generar credenciales.

El auto-registro del ESP32 en su primer arranque está pendiente de decisión. No debe habilitarse sin una credencial de bootstrap: la MAC es pública y falsificable, y un registro existente solo puede considerarse válido después de verificar el secreto individual.

Consulta [docs/architecture.md](docs/architecture.md) para el modelo y las decisiones pendientes, y [docs/api-examples.http](docs/api-examples.http) para ejemplos de llamadas.
