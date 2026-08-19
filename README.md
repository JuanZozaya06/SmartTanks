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
- **Desarrollo local:** Firebase Emulator Suite para Auth, Firestore y Functions.

No se usa MySQL ni Railway en esta versión. La API es la única que escribe: el ESP32 no recibe credenciales administrativas y el navegador queda limitado por las reglas de Firestore.

## Carpetas

```text
backend/                 Cloud Function Python y pruebas
frontend/                Aplicación Angular
docs/                    Arquitectura y contratos
.github/workflows/       Despliegue del panel
firebase.json            Functions, Firestore y emuladores
firestore.rules          Autorización de datos
firestore.indexes.json   Índices requeridos por consultas
```

## Primer arranque local

Requisitos: Node.js 24.15 o posterior (también sirve 22.22.3 o posterior), Python 3.12, Java y Firebase CLI.

```powershell
Copy-Item .firebaserc.example .firebaserc
# Editar .firebaserc con el project ID real.

py -3.12 -m venv backend\venv
backend\venv\Scripts\python -m pip install -r backend\requirements-dev.txt

Set-Location frontend
npm install
Set-Location ..

npx firebase-tools emulators:start
```

En otra terminal:

```powershell
Set-Location frontend
npm start
```

El panel abre en `http://localhost:4200`; la UI de emuladores, en `http://localhost:4000`.

`frontend/public/config.js` controla el destino mediante `useEmulators`. Con `false`, incluso `localhost` usa Firebase Auth, Firestore y la API productivos. Cambiarlo a `true` solo cuando Emulator Suite esté encendido; así las pruebas aisladas no escriben en producción.

## Despliegue

### Backend

1. Crear el proyecto en Firebase y activar Firestore y Authentication.
2. Cambiar el ID en `.firebaserc`.
3. Activar Blaze; Cloud Functions exige una cuenta de facturación aun cuando el uso quede dentro de la cuota sin costo.
4. Configurar `ALLOWED_ORIGINS` con el dominio real de GitHub Pages.
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
- `GET /v1/me/context` para recuperar usuario, casa y tanques.
- `POST /v1/homes` para crear perfil, casa, membresía `owner` y hasta dos tanques.
- `POST /v1/homes/{homeId}/devices/claim` para asociar mediante `deviceId + PIN + nombre`.
- `GET /v1/homes/{homeId}/devices` para listar los SmartTanks asociados.

La API productiva está desplegada en:

```text
https://us-east1-smarttanks-830ba.cloudfunctions.net/api
```

El panel no contiene datos demostrativos. Sin sesión muestra acceso; sin casa muestra la configuración inicial; con una casa válida muestra únicamente datos recibidos desde Firestore.

## Actualización en tiempo real

Al aceptar un lote nuevo, la API guarda el histórico en `readings` y actualiza `latestReading` dentro de `homes/{homeId}/tanks/{tankId}`. El panel escucha esos documentos con Firestore `onSnapshot()`, por lo que no consulta la API cada 30 segundos.

El usuario crea su cuenta desde Angular y completa el formulario con nombre de la casa, zona horaria, altura, diámetro, capacidad y umbral de nivel bajo de ambos tanques. La API crea la membresía y el panel obtiene el `homeId` desde `/v1/me/context`; no se configura manualmente en el frontend.

Antes de usar el registro, habilitar el proveedor **Correo electrónico/contraseña** en Firebase Authentication.

## Asociación de un SmartTank

Cada equipo debe existir previamente en `devices/{deviceId}` con estado `unclaimed`, un PIN de claim y un secreto individual. Firestore guarda solamente los hashes del PIN y del secreto. El `deviceId` usa el formato `smarttank-<MAC completa de 12 hex>`.

Desde **Agregar SmartTank**, el usuario final ingresa el ID y PIN impresos en el equipo, además de un nombre referencial. Si coinciden, la API asigna el equipo a la casa y conecta automáticamente el canal A con `tank_1` y el canal B con `tank_2`. No existe una ruta web para que el usuario genere credenciales.

El auto-registro del ESP32 en su primer arranque está pendiente de decisión. No debe habilitarse sin una credencial de bootstrap: la MAC es pública y falsificable, y un registro existente solo puede considerarse válido después de verificar el secreto individual.

Consulta [docs/architecture.md](docs/architecture.md) para el modelo y las decisiones pendientes, y [docs/api-examples.http](docs/api-examples.http) para ejemplos de llamadas.
