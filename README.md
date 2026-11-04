# NEUROPHOBIA — Backend

API REST del sistema NEUROPHOBIA, prototipo académico de realidad virtual para apoyar el tratamiento de la aracnofobia mediante exposición gradual. Trabajo de grado de **Sara María Ojeda López**, Ingeniería de Software, Universidad Cooperativa de Colombia (Pasto, 2026).

> NEUROPHOBIA no es un dispositivo médico ni sustituye a un terapeuta. Se usa con el acompañamiento de un profesional de la salud.

## Qué hace

- Cuentas y roles: paciente, profesional de la salud y administrador.
- Recepción de los registros de cada nivel que envía la app de realidad virtual (Meta Quest).
- Seguimiento del profesional: progreso de sus pacientes y notas.
- Módulo de IA: índice de tolerancia y recomendación al cerrar cada sesión. Primero una línea base de reglas; después, un modelo supervisado interpretable.

## Tecnologías

Python, FastAPI, PostgreSQL (con `JSONB` para los registros de sesión), Alembic y Docker. Arquitectura en capas: presentación, lógica de negocio, módulo de IA y acceso a datos.

## Contrato de la API

La especificación aprobada está en [`docs/api/CONTRATO_API_v1.md`](docs/api/CONTRATO_API_v1.md) (versión `contrato-v1.0.0`). **Este repositorio es su fuente**: la web y la app de realidad virtual guardan copias fijadas a una versión (`contrato-vX.Y.Z`).

- [`docs/api/openapi.json`](docs/api/openapi.json): OpenAPI generado por FastAPI. Se regenera con `python scripts/export_openapi.py`; una prueba falla si no está al día.
- [`docs/api/examples/`](docs/api/examples/): los ejemplos JSON del contrato, que usan las pruebas de los tres componentes.
- Documentación interactiva con la API en marcha: `http://localhost:8000/api/v1/docs`.

## Repositorios relacionados

- App de realidad virtual (Unity): https://github.com/sara9559ojeda/NPdefdef
- Web (React + TypeScript): https://github.com/sara9559ojeda/NP_Front

## Estructura

```
app/
├── api/            capa de presentación: rutas FastAPI y dependencias de autenticación por rol
├── services/       lógica de negocio: cuentas, permisos, seguimiento, visor, exportación
├── ai/             módulo de IA (no depende de la base de datos; separable como servicio)
│   ├── rules_baseline.py          línea base de reglas
│   └── rules_baseline_config.json umbrales provisionales, todos «pendiente de validar»
├── repositories/   acceso a datos de los esquemas identity y clinical
├── db/             modelos SQLAlchemy y sesión
├── schemas/        esquemas Pydantic (camelCase hacia fuera)
├── core/           configuración, seguridad, errores problem+json, logs, límites de frecuencia
└── cli.py          crear el primer administrador
alembic/            migraciones
tests/              pytest (PostgreSQL efímero en Docker)
docs/api/           contrato, openapi.json y ejemplos
```

## Puesta en marcha con Docker

Requisitos: Docker Desktop. Puertos: API **8000** y PostgreSQL **5433** (solo desde este PC).

1. Copia `.env.example` como `.env` y escribe los valores (el archivo `.env` no se sube a Git).
2. Levanta la API y la base de datos (las migraciones se aplican solas al arrancar):

   ```
   docker compose up -d --build
   ```

3. Crea el primer administrador (pide nombre, correo y contraseña por la terminal):

   ```
   docker compose exec api python -m app.cli create-admin
   ```

4. Comprueba: `http://localhost:8000/api/v1/health` → `{"status": "ok", "version": "0.1.0"}`.

Para que el visor se conecte por la Wi-Fi local (solo builds de desarrollo), usa la IP de este PC en lugar de `localhost`.

## Variables de entorno

| Variable | Obligatoria | Para qué |
|---|---|---|
| `POSTGRES_USER`, `POSTGRES_PASSWORD` | Sí (Docker) | Credenciales de PostgreSQL. Solo letras, números, `-` y `_`. |
| `POSTGRES_DB` | No | Nombre de la base (por defecto `neurophobia`). |
| `NP_SECRET_KEY` | Sí | Firma los JWT y protege los códigos de emparejamiento. Mínimo 32 caracteres. |
| `NP_DATABASE_URL` | Solo fuera de Docker | `postgresql+psycopg://usuario:contraseña@localhost:5433/base`. |
| `NP_CORS_ORIGIN` | No | Origen de la web (por defecto `http://localhost:5173`). |
| `NP_COOKIE_SECURE` | No | `true` por defecto (cookie de refresco `Secure`). |
| `NP_LOG_LEVEL` | No | `INFO` por defecto. |

Otras opciones técnicas (vida de los tokens, límites de frecuencia, tamaño máximo del sobre) están en `app/core/config.py` y se cambian con variables `NP_*` del mismo nombre.

## Pruebas

```
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
```

Las pruebas arrancan un PostgreSQL efímero en Docker con credenciales aleatorias y lo borran al terminar (o usan `NP_TEST_DATABASE_URL` si está definida). Cubren cada ruta con sus errores, la matriz de roles completa, la idempotencia y el desorden de `/device/records`, el emparejamiento, la retirada del consentimiento, los logs sin datos personales, el tiempo de respuesta, las migraciones y que `openapi.json` está al día. La integración continua (`.github/workflows/tests.yml`) las ejecuta en cada pull request.

## Módulo de IA

La primera versión es una línea base de reglas que se ejecuta al recibir el cierre de la sesión (`session_end`) y guarda el índice de tolerancia, la recomendación (`advance`, `repeat` o `step_back`) y su explicación (`basis`). **Ningún umbral tiene fuente clínica**: todos están en `app/ai/rules_baseline_config.json` marcados «provisional técnico, sin fuente, pendiente de validar», y la API devuelve `clinicalStatus: "pendiente_de_validar"`. La recomendación no cambia nada sola: el profesional decide el nivel inicial. Las sesiones de prueba (`testSession = true`) no se analizan ni se exportan.
