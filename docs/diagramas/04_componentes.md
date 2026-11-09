# Diagrama de componentes

Se proponen **cuatro hojas** en VP Online:

- Hoja A: vista general del sistema.
- Hoja B: componentes internos del backend.
- Hoja C: componentes internos de la web.
- Hoja D: componentes internos de la app VR.

Notación UML 2:

- **Component:** rectángulo con el icono de componente.
- **Interfaz ofrecida:** *Provided Interface*, el «lollipop» o círculo.
- **Interfaz requerida:** *Required Interface*, el semicírculo.
- **Conexión entre ambas:** *Assembly Connector*. Si se prefiere, *Dependency* punteada con `«use»`.

---

## Hoja A — Vista general

### Componentes

| Componente | Estereotipo | Tecnología | Repositorio |
|---|---|---|---|
| **App VR NEUROPHOBIA** | `«application»` | Unity 6000.3, OpenXR, XR Interaction Toolkit · APK Meta Quest 2/3/3S | NPdefdef |
| **Web NEUROPHOBIA** | `«application»` | React + TypeScript (Vite) · SPA | NP_Front |
| **Proxy web** | `«component»` | Función serverless Node (`api/proxy.mjs`) en Vercel; en AWS lo sustituye CloudFront | NP_Front / NP_Back infra |
| **API NEUROPHOBIA** | `«service»` | FastAPI · Python 3.12 · contenedor Docker | NP_Back |
| **Módulo de IA** | `«component»` (dentro de la API) | Reglas base `rules-baseline` | NP_Back `app/ai` |
| **Base de datos** | `«database»` | PostgreSQL 17 · esquemas `identity` y `clinical` | NP_Back `alembic/` |
| **Almacenamiento local del visor** | `«artifact»` / `«file»` | `persistentDataPath/outbox` (RecordOutbox) y `device_context.json` | NPdefdef |

### Interfaces

| Interfaz | Ofrece | Requiere | Detalle |
|---|---|---|---|
| **IWebAPI** `/api/v1/{auth, me, patients, admin, public, health}` | API NEUROPHOBIA | Proxy web → Web NEUROPHOBIA | JWT Bearer (acceso) + cookie HttpOnly (refresh) |
| **IDeviceAPI** `/api/v1/device/{pair, context, records, phobia-grade, sessions/{id}, unpair}` | API NEUROPHOBIA | App VR NEUROPHOBIA | Token opaco de dispositivo (Bearer) |
| **IProxy** `/api/v1/*` (mismo origen) | Proxy web | Web NEUROPHOBIA | Añade `x-np-proxy-secret` y `x-np-client-ip` |
| **SessionAnalyzer** | Módulo de IA | API NEUROPHOBIA (AnalysisService) | `analyze(SessionFeatures) : AnalysisResult` |
| **SQL / psycopg** | Base de datos | API NEUROPHOBIA | SQLAlchemy 2 + Alembic |
| **Archivos locales** | Almacenamiento local | App VR | Cola de envío que sobrevive sin red |

### Conectores

1. Web NEUROPHOBIA —`«use»` IProxy→ Proxy web
2. Proxy web —`«use»` IWebAPI→ API NEUROPHOBIA
3. App VR —`«use»` IDeviceAPI→ API NEUROPHOBIA (HTTPS; solo al terminar cada nivel, nunca durante la exposición)
4. App VR —`«use»`→ Almacenamiento local del visor
5. API NEUROPHOBIA —`«use»` SessionAnalyzer→ Módulo de IA. Dibujar el Módulo de IA **dentro** de la API.
6. API NEUROPHOBIA —`«use»` SQL→ Base de datos

> **Opcional, como diagrama de despliegue o nota:** en AWS (`infra/aws`) la cadena es *Amazon CloudFront* (`/*` → S3 con la web; `/api/v1/*` → ALB interno) → *ECS Fargate* (API) → *RDS PostgreSQL 17*. Los secretos están en *Secrets Manager* y los logs en *CloudWatch*. En Vercel, la web y su proxy están en Vercel, y la API en Vercel con PostgreSQL de Supabase.

---

## Hoja B — Backend (NP_Back)

Dibuja un componente contenedor **API NEUROPHOBIA**. Dentro van estos componentes:

| Componente | Módulo | Ofrece | Requiere |
|---|---|---|---|
| **Routers HTTP** | `app/api/routes` (auth, me, patients, admin, device, public, health) | IWebAPI, IDeviceAPI (puertos hacia fuera) | Autenticación y permisos, Servicios |
| **Autenticación y permisos** | `app/api/deps.py` | `current_actor`, `require_roles`, `current_device` | Servicio de cuentas/emparejamiento, Seguridad |
| **Servicio de cuentas** | `services/auth.py`, `accounts.py`, `admin.py` | IAccounts | Repositorio identity, Repositorio clinical, Limitador |
| **Servicio de emparejamiento** | `services/pairing.py` | IPairing | Repositorios, Limitador |
| **Servicio de registros del visor** | `services/records.py` | IRecords | Repositorio clinical, Servicio de análisis, Servicio de terapia |
| **Servicio de seguimiento** | `services/tracking.py`, `therapy.py` | ITracking | Repositorios |
| **Servicio de análisis** | `services/analysis.py` | IAnalysis | Módulo de IA, Repositorio clinical |
| **Módulo de IA** | `app/ai` | SessionAnalyzer | — |
| **Repositorio identity** | `repositories/identity.py` | IIdentityStore | ORM |
| **Repositorio clinical** | `repositories/clinical.py` | IClinicalStore | ORM |
| **ORM / sesión de BD** | `app/db` (models, session) | ISession | Base de datos (externa) |
| **Core transversal** | `app/core` (config, errors, security, ratelimit, logging, pagination) | Settings, ApiError, JWT/hash, Limitador | Base de datos (`rate_limit_events`) |

Puertos del contenedor: **IWebAPI** e **IDeviceAPI** hacia fuera, y **SQL** hacia la base de datos.

---

## Hoja C — Web (NP_Front)

Contenedor **Web NEUROPHOBIA (SPA)**:

| Componente | Módulo | Contenido |
|---|---|---|
| **Enrutador** | `App.tsx` (React Router) | Rutas `/`, `/registro`, `/iniciar-sesion`, `/cuenta`, `/paciente/*`, `/profesional/*`, `/admin/*` |
| **Contexto de autenticación** | `auth/AuthContext.tsx`, `RequireRole.tsx` | `AuthProvider`, `useAuth`, protección por rol |
| **Páginas públicas** | `pages/public` | HomePage, LoginPage, RegisterPage |
| **Páginas del paciente** | `pages/patient` | PatientHomePage, PatientSessionsPage, PatientSessionPage, PatientDevicesPage |
| **Páginas del profesional** | `pages/professional` | ProfessionalPatientsPage, ProfessionalPatientDetail y pestañas (Summary, Sessions, Session, Feedback, Notes, Plan) |
| **Páginas de administración** | `pages/admin` | AdminUsersPage, AdminAssignmentsPage, AdminExportPage |
| **Cuenta y errores** | `pages/AccountPage.tsx`, `ErrorPages.tsx` | AccountPage, ForbiddenPage, NotFoundPage |
| **Componentes de presentación** | `components/` (Layout, Clinical, PairingCodePanel, therapy, signature, ui) | Layout, gráfica de tolerancia, tablas, selector de grado, campos y avisos |
| **Hooks** | `hooks/useApi.ts` | `useApi`, `usePaged` |
| **Cliente de API** | `api/client.ts`, `endpoints.ts`, `adapters.ts`, `types.ts` | `request`, `refreshAccessToken`, `ApiError`; endpoints `auth`, `me`, `patients`, `admin`, `publicInfo` |
| **Textos (i18n)** | `i18n/` | `es.json` |
| **Simulador de API (solo desarrollo)** | `mocks/` (MSW) | Ofrece IWebAPI simulada |

Dependencias: Páginas → Contexto de auth, Hooks, Componentes de presentación, Textos. Hooks y Contexto de auth → Cliente de API. Cliente de API → **IProxy** (puerto hacia fuera). El Simulador de API se conecta en el mismo puerto, con la nota *solo en desarrollo*.

---

## Hoja D — App VR (NPdefdef)

Contenedor **App VR NEUROPHOBIA**:

| Componente | Clases principales | Ofrece / requiere |
|---|---|---|
| **Menú principal** | NeuroPhobiaMainMenuModern, NeuroPhobiaMenuBridge, ButtonManager | Requiere: Gestión de sesión, Cliente API |
| **Gestión de sesión** | SessionManager, LevelManager, GameStateManager, LevelBootstrap | Ofrece: ISession (`StartSession`, `AddLevelMetrics`, `EndSession`) · Requiere: Cliente API |
| **Niveles 1–5** | Controladores por escena (ver ficha 03, sección 5) | Requiere: ISession, Métricas, Estímulo, UI de sesión |
| **Métricas** | MetricsCollector, TaskManager, SessionReport, LevelMetrics | Ofrece: IMetrics (`BuildMetrics`) |
| **Estímulo (arañas)** | AranaController (IPhobiaStimulus), NPNaturalSpiderPatrol, Level3SpiderPatrolV2 | Ofrece: IPhobiaStimulus |
| **UI de sesión** | GlobalSessionUI, BreathingGuide, HUD por nivel | Requiere: ISession, Cliente API (estado de envío) |
| **Cliente API** | FastAPIClient, DeviceRecordMapper, NeuroPhobiaJson, DeviceContextDto | Requiere: **IDeviceAPI** (puerto hacia fuera), Bandeja de salida |
| **Bandeja de salida** | RecordOutbox | Requiere: almacenamiento local |
| **Entrada XR / escritorio** | XRBootstrap, NeuroPhobiaControlModeSelector, NeuroPhobiaDesktopController | Requiere: OpenXR / XR Interaction Toolkit (componente externo `«library»`) |
