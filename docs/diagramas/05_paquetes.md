# Diagrama de paquetes

En VP Online se usa la forma *Package*: una carpeta con pestaña, con paquetes anidados unos dentro de otros. Las dependencias van con *Dependency*, una flecha punteada con `«import»` o `«use»`. Todas las flechas de esta ficha salen de los `import` reales del código.

Se proponen cuatro hojas, como en la de componentes. También se puede hacer una sola: la hoja A con los paquetes B, C y D desplegados.

---

## Hoja A — Sistema

```
NEUROPHOBIA
├── NP_Front   (Web, React + TypeScript)
├── NP_Back    (API, FastAPI + PostgreSQL)
│   └── infra/aws (CDK, TypeScript)
└── NPdefdef   (App VR, Unity C#)
```

| De | A | Dependencia |
|---|---|---|
| NP_Front | NP_Back | `«use»` HTTP `/api/v1` (contrato v1) |
| NPdefdef | NP_Back | `«use»` HTTP `/api/v1/device` (contrato v1) |
| NP_Back::infra/aws | NP_Front | `«deploy»` (publica la web compilada en S3) |

Añade una nota: *El contrato `docs/api/CONTRATO_API_v1.md` vive en NP_Back; NP_Front y NPdefdef guardan una copia fijada.*

---

## Hoja B — NP_Back

### Paquetes

```
app
├── main            (crea la aplicación FastAPI)
├── cli             (comandos: crear administrador)
├── api
│   ├── routes      (auth, me, patients, admin, device, public, health)
│   ├── deps        (autenticación y roles)
│   └── docs        (respuestas de error para OpenAPI)
├── services        (auth, accounts, admin, pairing, records, tracking, therapy, analysis, actor)
├── repositories    (identity, clinical)
├── db              (models, session)
├── schemas         (common, accounts, tracking, device)
├── ai              (base, features, registry, rules_baseline)
└── core            (config, database_url, errors, security, ratelimit, logging, pagination)
alembic             (migraciones 0001–0003)
tests
infra/aws           (bin, lib: app-stack, data-stack, backend-service, web-distribution, monitoring)
```

### Dependencias

| De | A | Tipo |
|---|---|---|
| main | api::routes, core, schemas | `«import»` |
| cli | services, db, schemas, core | `«import»` |
| api::routes | services, api::deps, api::docs, schemas, core | `«import»` |
| api::deps | services, repositories, db, core | `«import»` |
| services | repositories, db, schemas, ai, core | `«import»` |
| repositories | db, core | `«import»` |
| db | core | `«import»` |
| core | db | `«import»` (solo `ratelimit` → `db.session`, dentro de una función) |
| ai | — | sin dependencias internas (paquete independiente) |
| schemas | — | sin dependencias internas |
| alembic | db | `«import»` |
| tests | app | `«import»` |

Hay dos detalles que merece la pena marcar con una nota en el diagrama:

1. `api::deps` usa `repositories::identity` directamente, sin pasar por `services`, para comprobar el usuario del token.
2. Hay una dependencia circular **core ↔ db**: `db.session` usa `core.config`, y `core.ratelimit` importa `db.session` de forma diferida.

---

## Hoja C — NP_Front

### Paquetes

```
src
├── main / App      (arranque y rutas)
├── pages
│   ├── public
│   ├── patient
│   ├── professional
│   └── admin       (+ AccountPage, ErrorPages)
├── components
│   ├── ui
│   ├── therapy
│   └── signature   (+ Layout, Clinical, PairingCodePanel)
├── auth            (AuthContext, RequireRole)
├── hooks           (useApi, usePrefersReducedMotion)
├── api             (client, endpoints, adapters, types, generated/openapi)
├── i18n            (es.json)
├── mocks           (MSW: handlers, fixtures)
├── styles
└── test
api/proxy.mjs       (función serverless de Vercel, fuera de src)
```

### Dependencias

| De | A |
|---|---|
| main / App | pages, auth, components |
| pages | components, auth, hooks, api, i18n |
| components | api, auth, hooks, i18n |
| auth | api |
| hooks | api, i18n |
| api | i18n |
| mocks | api |
| test | pages, components, api, mocks |

---

## Hoja D — NPdefdef (`Assets`)

### Paquetes propios

```
Assets
├── Scripts
│   ├── Control        (SessionManager, LevelManager, GameStateManager, LevelBootstrap, XRBootstrap…)
│   ├── Comunicacion   (FastAPIClient, DeviceRecordMapper, RecordOutbox, NeuroPhobiaJson)
│   ├── Metricas       (MetricsCollector, SessionReport, TaskManager)
│   ├── Entidades      (AranaController, IPhobiaStimulus)
│   ├── Menu           (NeuroPhobiaMenuBridge)
│   ├── UI             (GlobalSessionUI, BreathingGuide, NeuroPhobiaUITheme…)
│   ├── Nivel2 · Nivel3 · Nivel4 · Nivel5
├── Ajustes por nivel  (agrupa las carpetas NeuroPhobia_*)
│   ├── NeuroPhobia_MainMenuModern
│   ├── NeuroPhobia_Level1Flow
│   ├── NeuroPhobia_Levels123
│   ├── NeuroPhobia_Level23Polish
│   ├── NeuroPhobia_Level45     (namespace NeuroPhobia.Level45)
│   └── NeuroPhobia_PlayerFix
├── Scenes             (MainMenu, Nivel1…Nivel5)
├── Editor             (BuildQuest3, ContratoApiV1Tests)
└── Tests/PlayMode
```

Paquetes externos, con estereotipo `«library»`: **UnityEngine**, **Unity XR Interaction Toolkit 3.3.1**, **OpenXR**, **TextMeshPro**. Los modelos y texturas de terceros (`Modelosdetodo`, `Samples`) van en un paquete `«resources»` sin dependencias de código.

### Dependencias

| De | A |
|---|---|
| Control | Comunicacion, Metricas, Entidades |
| Comunicacion | Metricas (LevelMetrics, SessionReport) |
| Metricas | Control (SessionManager), Entidades (AranaController) |
| UI | Control, Comunicacion, Metricas |
| Menu | Control |
| Nivel2 … Nivel5 | Control, Metricas, Entidades, UI |
| Ajustes por nivel | Control, Metricas, UI, Comunicacion (solo MainMenuModern) |
| Scenes | Control, Metricas, UI, Nivel4, Nivel5, Ajustes por nivel |
| Editor | Comunicacion |
| Todos | UnityEngine; Control y Ajustes también XR Interaction Toolkit / OpenXR |

Nota para el diagrama: **Control ↔ Metricas** se dependen mutuamente, porque `MetricsCollector` usa `SessionManager.Instance` y `SessionManager` guarda `LevelMetrics`.
