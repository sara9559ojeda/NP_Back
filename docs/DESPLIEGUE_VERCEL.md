# Desplegar NP_Back en Vercel con PostgreSQL de Supabase

Este repositorio prepara el código; no crea recursos ni aplica cambios a tu base de datos durante el despliegue. Usar datos ficticios para la primera prueba.

## 1. Variables de Vercel (proyecto NP_Back)

Importa este repositorio, raíz `.`, preset FastAPI, Python 3.12 (fijado en `.python-version`). No sobrescribas Build Command ni Output Directory. `pyproject.toml` fija `main:app` y las dependencias, iguales a `requirements.txt`. No hace falta Docker en Vercel.

| Variable | Valor |
| --- | --- |
| `NP_DATABASE_URL` | URI de Transaction pooler de Supabase (6543), con esquema `postgresql+psycopg://` y `?sslmode=require` |
| `NP_SECRET_KEY` | Clave aleatoria de al menos 32 caracteres |
| `NP_PROXY_SECRET` | Otra clave aleatoria de al menos 32 caracteres; copiar exactamente la misma al servidor de NP_Front |
| `NP_CORS_ORIGIN` | URL HTTPS real de NP_Front, sin `/` final |
| `NP_COOKIE_SECURE` | `true` |
| `NP_LOG_LEVEL` | `INFO` |

Generar cada clave con `python -c "import secrets; print(secrets.token_urlsafe(48))"`. No compartirlas en chats, Git ni variables con prefijo VITE_. Las dos claves cumplen funciones distintas y deben tener valores diferentes.

En Supabase, Connect → Transaction pooler: copia host, usuario y base exactos. Sustituye solo el esquema por `postgresql+psycopg://`; agrega SSL. Si la contraseña lleva caracteres reservados, codifícala para URL. NP_DATABASE_URL es la conexión SQL, no la URL pública `https://...supabase.co` ni una API key.

Ejemplo ilustrativo, no una credencial:

```text
postgresql+psycopg://USUARIO:CLAVE_CODIFICADA@HOST:6543/postgres?sslmode=require
```

No se usan `SUPABASE_ANON_KEY`, `SUPABASE_SERVICE_ROLE_KEY` ni Supabase Auth. Las cuentas y permisos siguen en FastAPI. No se requieren `POSTGRES_*` en Vercel: pertenecen al Compose local.

## 2. Migraciones (antes de probar registro/login)

Ya existen dos migraciones versionadas:

- `0001_initial_schema.py`: esquemas identity/clinical y tablas del sistema.
- `0002_shared_rate_limits.py`: eventos de límites de frecuencia compartidos entre instancias.

Se ejecutan una vez por base y Alembic omite las ya aplicadas. No se ejecutan al iniciar cada función de Vercel.

En CMD, dentro de NP_Back:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
```

Configura las variables en esa terminal usando la URI **Session pooler (5432)** de Supabase para las operaciones administrativas:

```cmd
set "NP_DATABASE_URL=postgresql+psycopg://USUARIO:CLAVE_CODIFICADA@HOST:5432/postgres?sslmode=require"
python -m alembic upgrade head
python -m alembic current
```

La revisión final debe ser `0002`. La URI anterior es un ejemplo: reemplázala por tu conexión real. Si usas PowerShell, la asignación es `$env:NP_DATABASE_URL='URI_REAL'`. No guardes el secreto en archivos versionados. Un `.env` por sí solo no se carga automáticamente en estos comandos.

El usuario usado para migrar necesita crear esquemas y tablas. Conserva identity/clinical fuera de los esquemas expuestos a la Data API de Supabase; no concedas acceso a anon/authenticated a esas tablas. El frontend solo llama a FastAPI.

Si tu base ya está en `0001`, ejecuta igualmente `upgrade head`: solo se aplicará `0002`. No uses `stamp head` para saltarte la creación de tablas y no ejecutes el SQL completo sobre una base que ya las contiene.

## 3. Primer administrador

En la misma terminal, añade NP_SECRET_KEY (el mismo valor configurado en Vercel) y crea el administrador mediante la herramienta existente:

```cmd
set "NP_SECRET_KEY=TU_CLAVE_DEL_BACKEND"
python -m app.cli create-admin
```

El comando pide nombre, correo y contraseña. Ningún administrador ni contraseña real se incorpora al código.

## 4. Desplegar y conectar

Despliega NP_Back. Guarda la URL asignada por Vercel. En NP_Front configura `NP_BACKEND_ORIGIN` con ese origen HTTPS, sin rutas ni query, y la misma `NP_PROXY_SECRET`.

El frontend incorpora una función proxy en lugar de una URL ficticia en un rewrite. Preserva Cookie/Set-Cookie y acredita la IP con el secreto compartido. El backend ignora IPs personalizadas que no estén autenticadas. En peticiones directas a Vercel usa `x-vercel-forwarded-for`; fuera de Vercel usa la conexión directa. Nunca se confía indiscriminadamente en X-Forwarded-For.

El contador por IP reside en PostgreSQL, con bloqueo transaccional y hashes HMAC, no en memoria de la función. Su transacción es independiente: un intento fallido sigue contando. Se depuran eventos vencidos por clave y eventos abandonados de más de un día en lotes acotados. El proxy y los endpoints de autenticación no deben cachearse. Las IPs compartidas por NAT siguen compartiendo cuota, como corresponde a un límite por IP; no es protección completa contra ataques distribuidos.

El emparejamiento conserva la política de contar fallos; varias peticiones fallidas simultáneas pueden cruzar la comprobación antes de que se registren todas. No se presenta este limitador como una garantía exacta ante ráfagas concurrentes de emparejamiento.

## 5. Validación después del despliegue

1. GET `/api/v1/health` en backend y en dominio del frontend: ambos deben devolver JSON.
2. Registro e inicio de sesión con cuentas de prueba.
3. Recarga, refresh y logout: cookie HttpOnly/Secure/SameSite=Strict bajo `/api/v1/auth`.
4. Paciente no accede a admin/profesional; profesional no accede a pacientes ajenos.
5. Revisar notas, visor, sesiones incompletas y exportación.
6. Confirmar los resultados del CI en el PR y después verificar logs del despliegue sin exponer secretos.

`health` no comprueba todas las tablas. Un 200 no sustituye la prueba de registro/login ni las migraciones.

Si Vercel protege el backend con autenticación de previews, el proxy no podrá acceder sin configurar un mecanismo de acceso de servidor. Para la primera prueba usa el dominio estable del backend con la protección de despliegue configurada conscientemente; la API mantiene su propia autenticación por rol. No desactives protecciones de otros proyectos.

Referencias: [FastAPI en Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [conexiones Supabase](https://supabase.com/docs/guides/database/connecting-to-postgres), [sentencias preparadas](https://supabase.com/kb/troubleshooting/disabling-prepared-statements-qL8lEL).
