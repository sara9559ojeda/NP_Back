# Contrato de la API v1 — NEUROPHOBIA

- **Versión:** `contrato-v1.1.0` (04-11-2026), **aprobada por Sara María Ojeda López el 09-11-2026**. Cambios compatibles hacia atrás sobre `contrato-v1.0.0` (aprobada el 30-10-2026) para cubrir los diagramas UML/BPMN; ver sección 12. Cualquier cambio necesita una nueva aprobación y una versión nueva. **Este repositorio (NP_Back) es la fuente del contrato.**
- **Fecha:** 30-10-2026 (v1.0.0) · 04-11-2026 (v1.1.0)
- **Partes:** app VR (Unity, Meta Quest; repo NPdefdef), backend (FastAPI + PostgreSQL; repo NP_Back) y web (React + TypeScript; repo NP_Front).
- **Fuentes:** documento de metodología (RQF001–RQF015, RQFN001–RQFN010, HU-01 a HU-14) y decisiones de diseño aprobadas D1–D24.
- **Decisiones incorporadas (D18–D24):** quien se registra solo queda como paciente sin profesional asignado; el registro pide nombre, correo, contraseña y aceptación; el código de vinculación del visor lo generan el paciente o su profesional; el administrador no ve datos clínicos; los cuestionarios FSQ, SUS, IPQ y SSQ quedan fuera de la v1; el plazo de conservación lo fija el asesor o el comité de ética; en desarrollo el backend corre en Docker local.

---

## 1. Reglas generales

| Tema | Regla |
|---|---|
| Base | `https://<host>/api/v1`. En desarrollo, `http://localhost:8000/api/v1` (solo builds de desarrollo, ver D16 de R1 y RQFN003). |
| Formato | JSON UTF-8. Campos en `camelCase` (el backend usa `snake_case` por dentro, con alias). |
| Identificadores | UUID v4 en texto. Los que nacen en el visor (`sessionId`, `recordId`) los genera el visor. |
| Fechas | ISO 8601 en UTC con `Z` (`2026-10-30T21:05:00Z`). |
| Versiones | Ruta `/api/v1`. Cada registro del visor lleva `schemaVersion` (entero, hoy `1`). |
| Paginación | `?limit=` (por defecto 20, máximo 100) y `?cursor=`. Respuesta: `{ "items": [...], "nextCursor": "…" \| null }`. |
| Errores | `application/problem+json` (RFC 9457), ver sección 8. |
| Tiempo de respuesta | Menos de 2 s en condiciones normales (RQFN002). Objetivo interno: p95 < 500 ms. |
| Datos sensibles | **Nunca en la URL ni en los logs**: ni correos, ni nombres, ni tokens, ni cuerpos de petición. Los identificadores en la ruta son UUID aleatorios. |
| Documentación | El backend publica `openapi.json` generado por FastAPI y lo guarda en `docs/api/openapi.json`. La web genera sus tipos TypeScript a partir de ese archivo. |

---

## 2. Roles y autenticación

### 2.1 Roles (RQF004, RQFN004)

| Rol | Quién | Cómo se autentica |
|---|---|---|
| `anonymous` | Usuario externo sin cuenta | — |
| `patient` | Hace las sesiones VR y gestiona sus datos | Web: correo y contraseña. Visor: token de dispositivo |
| `professional` | Hace seguimiento a **sus** pacientes y escribe notas | Web: correo y contraseña |
| `admin` | Gestiona perfiles, roles y asignaciones | Web: correo y contraseña |

### 2.2 Tokens

| Token | Para | Vida | Dónde se guarda |
|---|---|---|---|
| Acceso (JWT firmado, `Authorization: Bearer`) | Web | 15 min | En memoria del navegador |
| Refresco (opaco, rotativo) | Web | 7 días | Cookie `HttpOnly`, `Secure`, `SameSite=Strict`, ruta `/api/v1/auth` |
| Dispositivo (opaco, revocable) | Visor | Hasta que se revoque | Almacenamiento privado de la app en el visor |

- Las contraseñas se guardan con **Argon2id** (RQFN003).
- La clave de firma y la cadena de conexión van en variables de entorno. **Nunca en el repositorio.** Las escribe Sara.
- El JWT solo lleva `sub` (UUID del usuario), `role` y `exp`. Nada de nombre ni correo.

### 2.3 Matriz de acceso

| Recurso | anonymous | patient | professional | admin |
|---|---|---|---|---|
| Registro, inicio de sesión | ✅ | — | — | — |
| Información del producto (`/public/*`, v1.1.0) | ✅ | ✅ | ✅ | ✅ |
| `/me` (datos propios) | — | ✅ | ✅ | ✅ |
| Códigos de emparejamiento | — | ✅ propios | ✅ de sus pacientes | — |
| `/device/*` (visor) | — | ✅ con token de dispositivo | — | — |
| Progreso y sesiones de un paciente | — | ✅ solo los propios | ✅ solo sus pacientes asignados | ❌ (ver nota) |
| Estado de la terapia y grado de fobia (v1.1.0) | — | ✅ propios (web y visor) | ❌ (ve el grado en `/patients`) | ❌ |
| Retroalimentación de IA por sesión (v1.1.0) | — | ✅ propia (en `/me/therapy` y detalle) | ✅ de sus pacientes | ❌ |
| Notas | — | ❌ | ✅ de sus pacientes | ❌ |
| Plan del paciente (nivel inicial permitido) | — | ❌ | ✅ de sus pacientes | — |
| Usuarios, roles, asignaciones | — | — | — | ✅ |
| Exportación anónima para análisis | — | — | — | ✅ |

> **Nota:** el administrador gestiona perfiles, pero **no** ve datos clínicos (minimización, Ley 1581). Si el asesor prefiere otra cosa, se cambia en D21.
> Si un profesional pide un paciente que no es suyo, la respuesta es **404**, no 403, para no revelar que existe.

---

## 3. Modelo de datos

Separación de identidad y datos clínicos (D15 de R1). Es el modelo implementado en `app/db/models.py` (migraciones en `alembic/`). Convenciones: **PK** = clave primaria, **FK** = clave foránea, **UQ** = único, `?` = admite nulo. Las fechas son `timestamptz`, los identificadores `uuid` y los `JSONB` guardan el registro completo del visor.

### 3.1 Esquema `identity` (cuentas, roles y consentimiento)

| Tabla | Columnas | Claves |
|---|---|---|
| `users` | `id`, `email`, `password_hash?`, `role`, `active`, `created_at`, `updated_at?`, `withdrawn_at?` | PK `id` · UQ `email` |
| `personal_data` | `user_id`, `full_name`, `updated_at` | PK y FK `user_id` → `users.id` (borrado en cascada) |
| `consents` | `id`, `user_id`, `consent_version`, `granted_at`, `withdrawn_at?` | PK `id` · FK `user_id` → `users.id` |
| `identity_links` | `user_id`, `pseudonym_id` | PK y FK `user_id` → `users.id` · UQ `pseudonym_id` (**sin FK**, ver 3.3) |
| `assignments` | `id`, `professional_user_id`, `patient_user_id`, `active`, `created_at`, `ended_at?` | PK `id` · FK `professional_user_id` y `patient_user_id` → `users.id` · índice único de la asignación activa |
| `refresh_tokens` | `id`, `user_id`, `family_id`, `token_hash`, `created_at`, `expires_at`, `revoked_at?` | PK `id` · FK `user_id` → `users.id` · UQ `token_hash` · `family_id` agrupa la rotación (no es FK) |
| `rate_limit_events` | `id`, `key_hash`, `occurred_at` | PK `id` (entero) · índices por `key_hash` y por fecha. Límite de frecuencia de inicio de sesión, registro y emparejamiento; guarda solo un hash de la clave, nunca correos ni IP en claro |

### 3.2 Esquema `clinical` (datos de terapia, seudonimizados)

| Tabla | Columnas | Claves |
|---|---|---|
| `patients` | `pseudonym_id`, `allowed_start_level`, `plan_updated_at?`, `phobia_grade?`, `phobia_grade_updated_at?`, `retain_until?`, `created_at` | PK `pseudonym_id`. `retain_until` queda preparado para el plazo de conservación (D23, pendiente) |
| `pairing_codes` | `id`, `pseudonym_id`, `code_hash`, `created_at`, `expires_at`, `used_at?` | PK `id` · FK `pseudonym_id` → `patients` · UQ `code_hash`. Código de un solo uso (10 min); se guarda solo su hash |
| `devices` | `id`, `pseudonym_id`, `model`, `app_version`, `token_hash`, `paired_at`, `last_seen_at?`, `revoked_at?` | PK `id` · FK `pseudonym_id` → `patients` · UQ `token_hash` |
| `sessions` | `id`, `pseudonym_id`, `device_id?`, `has_start`, `has_end`, `started_at?`, `ended_at?`, `phobia_grade?`, `test_session?`, `app_version?`, `device_model?`, `end_reason?`, `level_reached?`, `total_duration_seconds?`, `raw` (JSONB), `created_at` | PK `id` (lo genera el visor) · FK `pseudonym_id` → `patients` · FK `device_id` → `devices` (nulo si se revoca) · índice (`pseudonym_id`, `started_at`). `has_start` y `has_end` indican qué sobres han llegado, porque pueden llegar desordenados |
| `level_records` | `id`, `session_id`, `level`, `attempt`, `outcome`, `criterion_met`, `started_at`, `ended_at`, `permanence_seconds`, `min_distance_m?`, `avoidance_count`, `payload` (JSONB), `received_at` | PK `id` (= `recordId` del visor) · FK `session_id` → `sessions` |
| `analyses` | `session_id`, `method`, `method_version`, `tolerance_index`, `recommendation`, `basis` (JSONB), `clinical_status`, `created_at` | PK (`session_id`, `method`) · FK `session_id` → `sessions` |
| `notes` | `id`, `pseudonym_id`, `session_id?`, `author_user_id`, `text`, `created_at`, `edited_at?` | PK `id` · FK `pseudonym_id` → `patients` · FK `session_id` → `sessions` (nulo si se borra) · `author_user_id` **sin FK** (ver 3.3) |
| `inbound_records` | `record_id`, `pseudonym_id`, `device_id?`, `session_id`, `type`, `schema_version`, `content_hash`, `received_at` | PK `record_id` · índice `session_id` · **sin FK** (ver 3.3). Registro de idempotencia de `POST /device/records`: el mismo `recordId` con el mismo `content_hash` → `duplicate`; con otro → `409` |

### 3.3 Relaciones sin clave foránea (decisión de diseño)

En el diagrama entidad-relación se dibujan con **línea discontinua** y esta nota:

| Relación lógica | Por qué no tiene FK |
|---|---|
| `identity.identity_links.pseudonym_id` → `clinical.patients.pseudonym_id` | Es el único puente entre los dos esquemas. Sin FK, `clinical` no depende de `identity`: al retirar el consentimiento se borra el vínculo y los datos clínicos quedan anónimos (Ley 1581). Solo la capa de servicio une ambos lados |
| `clinical.notes.author_user_id` → `identity.users.id` | Cruza de `clinical` a `identity` por la misma separación. Si se borra la identidad del autor, la nota se conserva |
| `clinical.inbound_records` → `sessions`, `devices` y `patients` | El visor puede enviar un `level_record` o un `session_end` antes que su `session_start` (sección 6.3). Una FK rechazaría esos registros; el servicio los guarda y los enlaza después |

### 3.4 Reglas

- Solo la capa de servicio une `identity` y `clinical`, y siempre a través de `identity_links`.
- Los registros del visor se guardan completos en `JSONB` (`raw`, `payload`) y, además, en columnas los campos que se consultan.
- **Retirar el consentimiento** borra `personal_data` e `identity_links`, marca `users.withdrawn_at`, desactiva la cuenta y deja los datos clínicos sin vínculo (anónimos). El plazo de conservación (`patients.retain_until`) está pendiente (D23).
- Los secretos (contraseñas, tokens de refresco, tokens de dispositivo y códigos de emparejamiento) nunca se guardan en claro: solo su hash.

---

## 4. Rutas: cuentas y perfiles (web)

### 4.1 Registro — `POST /auth/register` (HU-06, RQF001)

```json
{
  "fullName": "Ana Pérez",
  "email": "ana@example.com",
  "password": "********",
  "consent": { "accepted": true, "consentVersion": "2026-10-v1" }
}
```

- `201` → `{ "userId": "…", "role": "patient" }`. El rol de un registro propio depende de D18.
- `409 EMAIL_TAKEN` si el correo existe (lo pide HU-06; se limita la frecuencia para evitar enumeración).
- `422 CONSENT_REQUIRED` si `consent.accepted` no es `true`.
- Los campos obligatorios definitivos dependen de D19.

### 4.2 Sesión web (HU-07, RQF003)

| Ruta | Cuerpo | Respuesta |
|---|---|---|
| `POST /auth/login` | `{ "email", "password" }` | `200 { "accessToken", "expiresIn", "user": { "id", "role" } }` y cookie de refresco. `401 INVALID_CREDENTIALS` sin decir qué falló. `423 ACCOUNT_DISABLED`. |
| `POST /auth/refresh` | — (cookie) | `200 { "accessToken", "expiresIn" }`. Rota la cookie. |
| `POST /auth/logout` | — | `204`. Revoca el refresco. |

### 4.3 Datos propios (HU-09, RQF006)

| Ruta | Descripción |
|---|---|
| `GET /me` | `{ "id", "role", "fullName", "email", "consents": [...] }` |
| `PATCH /me` | `{ "fullName"?, "email"? }` → `200` o `422` con `errors[]` por campo. |
| `PUT /me/password` | `{ "currentPassword", "newPassword" }` → `204` |
| `POST /me/consents/withdraw` | Retira el consentimiento → `202`. Ver sección 3. |

### 4.4 Administración (HU-10, RQF005)

| Ruta | Descripción |
|---|---|
| `GET /admin/users?role=&active=&q=` | Lista paginada (`id`, `fullName`, `email`, `role`, `active`). |
| `POST /admin/users` | `{ "fullName", "email", "role", "temporaryPassword" }` → `201` |
| `GET /admin/users/{userId}` | **v1.1.0.** Perfil de un usuario (mismos campos que la lista). `404` si no existe. |
| `PATCH /admin/users/{userId}` | `{ "role"?, "active"?, "fullName"?, "email"? }` → `200`. `409 LAST_ADMIN` si se quita el último admin; `409 EMAIL_TAKEN` si el correo ya existe. `fullName` y `email` son **v1.1.0**. |
| `PUT /admin/users/{userId}/password` | **v1.1.0.** `{ "temporaryPassword" }` → `204`. Cierra todas las sesiones web de ese usuario. |
| `GET /admin/assignments?professionalId=` | Asignaciones profesional–paciente. |
| `POST /admin/assignments` | `{ "professionalId", "patientId" }` → `201` |
| `DELETE /admin/assignments/{assignmentId}` | `204` |
| `GET /admin/exports/analysis-dataset` | Exportación **anónima**: sin `pseudonym_id`, con identificadores nuevos en cada exportación; excluye `testSession = true`. JSON o CSV (`Accept`). |

---

## 5. Rutas: seguimiento (web)

### 5.1 Profesional (HU-12, HU-13, RQF014, RQF015)

| Ruta | Descripción |
|---|---|
| `GET /patients` | Pacientes asignados: `{ "patientId", "fullName", "lastSessionAt", "levelReached", "lastRecommendation", "phobiaGrade" }` (`phobiaGrade` desde v1.1.0). |
| `GET /patients/{patientId}/progress` | Igual que `GET /me/progress`, para ese paciente. |
| `GET /patients/{patientId}/sessions` | Lista paginada de sesiones. |
| `GET /patients/{patientId}/sessions/{sessionId}` | Detalle: sesión, registros por nivel, SUDS y análisis. |
| `PUT /patients/{patientId}/plan` | `{ "allowedStartLevel": 1–5 }`. Nivel inicial permitido (HU-08, RQF009). Por defecto, 1. |
| `GET /patients/{patientId}/notes` | Notas paginadas, más recientes primero. **v1.1.0:** `?sessionId=` filtra por sesión. |
| `POST /patients/{patientId}/notes` | `{ "text", "sessionId"? }` → `201 { "noteId", "createdAt" }`. **v1.1.0:** devuelve además `sessionId`, `authorId`, `authorName`, `text`, `editedAt` («comentario anotado»). |
| `GET /patients/{patientId}/feedback` | **v1.1.0.** «Consultar retroalimentación»: paginado, más recientes primero. `items[]`: `{ "sessionId", "startedAt", "endedAt", "phobiaGrade", "levelReached", "endReason", "notesCount", "analysis" }` (`analysis` como en la sección 7). Solo sesiones con análisis guardado. |
| `PATCH /patients/{patientId}/notes/{noteId}` | Solo el autor. Guarda `editedAt`. |

### 5.2 Paciente (HU-05, RQF013)

| Ruta | Descripción |
|---|---|
| `GET /me/progress` | `{ "sessionsCount", "levelReached", "lastSessions": [ { "sessionId", "startedAt", "levelReached", "totalDurationSeconds", "recommendation" } ] }` |
| `GET /me/sessions` y `GET /me/sessions/{sessionId}` | Igual que en el profesional, sin notas. |
| `GET /me/therapy` | **v1.1.0.** Estado para «Iniciar terapia»: `{ "phobiaGrade", "phobiaGradeUpdatedAt", "allowedStartLevel", "pairedDevices", "openSession": { "sessionId", "startedAt" } \| null, "lastSession", "lastFeedback": { "sessionId", "startedAt", "endedAt", "phobiaGrade", "levelReached", "endReason", "analysis" } \| null }`. |
| `PUT /me/phobia-grade` | **v1.1.0.** «Ajustar grado de fobia»: `{ "phobiaGrade": 1–5 }` → `200 { "phobiaGrade", "updatedAt" }`. |

---

## 6. Rutas: visor (app Unity)

### 6.1 Emparejamiento del visor (D15 de R1)

1. En la web, el paciente (o su profesional) pide un código: `POST /pairing-codes` (paciente) o `POST /patients/{patientId}/pairing-codes` (profesional) → `201 { "code": "K7Q-4MZ", "expiresAt": "…" }`. Seis caracteres sin ambigüedades (sin 0/O, 1/I), válido 10 minutos y de un solo uso.
2. En el visor, la persona lo escribe: `POST /device/pair`

```json
{ "code": "K7Q-4MZ", "deviceModel": "quest3", "appVersion": "0.2.0" }
```

→ `201 { "deviceId": "…", "deviceToken": "…" }`. `410 PAIRING_CODE_EXPIRED`, `404 PAIRING_CODE_INVALID`, `429` tras 5 intentos fallidos.

3. Desde la web se puede revocar: `GET /me/devices`, `DELETE /me/devices/{deviceId}` → `204`. Un token revocado devuelve `401 DEVICE_REVOKED` y la app vuelve a pedir código.

### 6.2 Contexto al empezar — `GET /device/context`

Con el token de dispositivo. La app lo pide **en el Refugio**, nunca durante la exposición.

```json
{
  "allowedStartLevel": 1,
  "lastSession": { "endedAt": "2026-10-29T20:10:00Z", "levelReached": 2, "totalDurationSeconds": 612 },
  "recommendation": {
    "value": "repeat",
    "fromSessionId": "…",
    "method": "rules-baseline",
    "clinicalStatus": "pendiente_de_validar"
  }
}
```

- No incluye nombre ni correo.
- Sin conexión, la app usa la última copia guardada y, si no hay ninguna, empieza en el nivel 1.
- **v1.1.0:** añade `"phobiaGrade": 1–5 | null` y `"phobiaGradeUpdatedAt"`: el último grado de fobia autorreportado, para precargar el paso «Ajustar grado de fobia» (ejemplo `device_context.v1_1.response.200.json`).

### 6.3 Envío de registros — `POST /device/records`

Un único punto de entrada para la bandeja de salida (D12 de R1). Cada archivo de la bandeja es un sobre:

```json
{
  "recordId": "6f1c…",
  "type": "session_start | level_record | session_end",
  "schemaVersion": 1,
  "sessionId": "a3b9…",
  "payload": { }
}
```

| Respuesta | Significado | Qué hace la app |
|---|---|---|
| `201 { "status": "stored" }` | Guardado | Borra el archivo |
| `200 { "status": "duplicate" }` | Ya existía con el mismo contenido (idempotente por `recordId`) | Borra el archivo |
| `409 RECORD_CONFLICT` | Mismo `recordId` con contenido distinto | Cuarentena |
| `422 VALIDATION_ERROR` | El sobre no cumple el esquema | Cuarentena |
| `401` | Token inválido o revocado | Conserva y pide emparejar |
| `429`, `5xx`, sin red | Fallo temporal | Reintenta con espera creciente |
| `503 STORAGE_UNAVAILABLE` (v1.1.0) | La base de datos no respondió; **no se guardó nada** (ni métricas ni análisis) | Muestra el mensaje de error y reintenta el mismo sobre tras `Retry-After` |

**v1.1.0:** las respuestas `201`/`200` añaden dos campos opcionales (la app v1 puede ignorarlos):

```json
{
  "status": "stored",
  "session": { "sessionId": "…", "status": "open | closed | pending_start" },
  "feedback": {
    "status": "saved | pending | not_applicable | insufficient_data",
    "recommendation": "repeat", "toleranceIndex": 0.62, "method": "rules-baseline",
    "clinicalStatus": "pendiente_de_validar", "createdAt": "2026-10-30T21:12:01Z"
  }
}
```

`feedback.status`: `saved` = análisis guardado («retroalimentación guardada»); `pending` = falta el inicio o el cierre; `not_applicable` = sesión de prueba; `insufficient_data` = cerrada sin datos suficientes. Métricas, análisis y retroalimentación se guardan en **una sola transacción**: o todo o nada.

- Orden: el backend acepta un `level_record` o un `session_end` aunque aún no haya llegado su `session_start` (los guarda pendientes de enlazar). La red no garantiza el orden.
- **«Responder sin guardar» no llama a esta ruta.** Nada sale del visor.
- Tamaño máximo por sobre: 256 KB.

#### `payload` de `session_start`

```json
{
  "startedAt": "2026-10-30T21:00:00Z",
  "phobiaGrade": 3,
  "appVersion": "0.2.0",
  "deviceModel": "quest2 | quest3 | quest3s | editor",
  "testSession": false
}
```

`phobiaGrade`: 1–5 (RQF007, HU-08). `testSession`: `true` si se abrió con el selector de nivel (D17); esas sesiones se excluyen del análisis.

#### `payload` de `level_record` (HU-04, RQF011)

```json
{
  "level": 1,
  "attempt": 1,
  "levelDefinitionVersion": "2026-10-30",
  "startedAt": "2026-10-30T21:01:10Z",
  "endedAt": "2026-10-30T21:05:40Z",
  "outcome": "completed | criterion_not_met | safe_exit | abandoned",
  "criterionMet": true,
  "permanenceSeconds": 270.0,
  "minDistanceM": 1.85,
  "gaze": { "coneDeg": 15, "onStimulusSeconds": 142.5, "meanAngleDeg": 21.3 },
  "avoidanceCount": 2,
  "suds": [
    { "phase": "before", "value": 60, "at": 0.0 },
    { "phase": "during", "value": 70, "at": 120.4 },
    { "phase": "after",  "value": 40, "at": 270.0 }
  ],
  "events": [
    { "t": 0.0,   "type": "level_start" },
    { "t": 33.2,  "type": "avoidance", "data": { "retreatSpeed": 0.9 } },
    { "t": 80.0,  "type": "pause" },
    { "t": 95.0,  "type": "resume" },
    { "t": 270.0, "type": "level_end" }
  ],
  "samples": { "hz": 2, "distanceM": [3.1, 3.0], "angleDeg": [12.0, 8.5] },
  "extra": {
    "taskCompletions": ["TASK_LAMP"],
    "breathingActivations": 0,
    "headMovementMean": 0.12,
    "handContactSeconds": 0.0,
    "handWithdrawals": 0
  }
}
```

- La «mirada» es la **orientación de la cabeza**: Quest 2 y 3 no tienen seguimiento ocular.
- `minDistanceM` es `null` si el nivel no tuvo estímulo muestreado (sustituye al `-1` actual).
- `suds[].value`: entero 0–100 (Wolpe, 1969). La frecuencia del «durante» está pendiente de validar.
- `events[].type` permitidos: `level_start`, `level_end`, `pause`, `resume`, `avoidance`, `suds`, `safe_exit`, `repeat_offered`, `repeat_accepted`, `tutorial_skipped`.
- `extra` conserva las métricas que ya mide el proyecto actual (`LevelMetrics`) para no perderlas.

#### `payload` de `session_end`

```json
{
  "endedAt": "2026-10-30T21:12:00Z",
  "endReason": "completed | user_finished | safe_exit | app_closed",
  "levelReached": 2,
  "totalDurationSeconds": 720.0
}
```

Al recibir `session_end`, el backend lanza el análisis (sección 7).

### 6.4 Ajustar grado de fobia en el visor — `PUT /device/phobia-grade` (v1.1.0)

Con el token de dispositivo, en el Refugio y antes de «Comenzar» (BPMN). `{ "phobiaGrade": 1–5 }` → `200 { "phobiaGrade", "updatedAt" }`. El `phobiaGrade` del `session_start` sigue siendo obligatorio; si es más reciente que el último ajuste, también actualiza el grado guardado.

### 6.5 Estado de una sesión — `GET /device/sessions/{sessionId}` (v1.1.0)

`200 { "sessionId", "status", "startedAt", "endedAt", "phobiaGrade", "levelReached", "levelsStored", "feedback" }` (`feedback` como en 6.3). `404` si la sesión no es de ese paciente. Sirve para confirmar «retroalimentación guardada» tras el `session_end`.

### 6.6 Cerrar sesión en el visor — `POST /device/unpair` (v1.1.0)

`204`. Revoca el propio token del visor; las siguientes llamadas responden `401 DEVICE_REVOKED` y hace falta un código nuevo.

---

## 7. Análisis de IA (HU-11, RQF012)

- Se calcula **al cerrar la sesión**, no en tiempo real (D13 de R1).
- Resultado guardado en `analyses` y expuesto en el detalle de la sesión y en `GET /device/context`:

```json
{
  "toleranceIndex": 0.62,
  "recommendation": "advance | repeat | step_back",
  "method": "rules-baseline",
  "methodVersion": "0.1.0",
  "basis": [
    { "feature": "sudsDrop", "value": 20, "effect": "favorable" },
    { "feature": "avoidanceCount", "value": 2, "effect": "unfavorable" }
  ],
  "clinicalStatus": "pendiente_de_validar"
}
```

- `toleranceIndex` va de 0 a 1. `basis` explica en qué se basa, para que el profesional lo entienda (apartado 3.6.3 del documento).
- **Primera versión:** reglas. Los umbrales **no se inventan**: mientras no los valide un profesional, el backend los deja como parámetros con `clinicalStatus: "pendiente_de_validar"` y la web lo muestra así.
- **Segunda versión:** modelo supervisado interpretable (árbol de decisión o regresión logística, scikit-learn) entrenado con la SUDS como etiqueta, solo con datos anónimos y sin `testSession`.
- La recomendación **no cambia nada sola**: el profesional decide el nivel inicial permitido con `PUT /patients/{patientId}/plan`.

---

## 8. Errores

Formato (RFC 9457):

```json
{
  "type": "https://neurophobia/errors/validation-error",
  "title": "Datos no válidos",
  "status": 422,
  "code": "VALIDATION_ERROR",
  "detail": "Revisa los campos marcados.",
  "errors": [ { "field": "email", "code": "invalid_format" } ]
}
```

| HTTP | `code` | Cuándo |
|---|---|---|
| 400 | `BAD_REQUEST` | JSON mal formado |
| 401 | `UNAUTHENTICATED`, `TOKEN_EXPIRED`, `INVALID_CREDENTIALS`, `DEVICE_REVOKED` | Sin token, token caducado, credenciales malas, visor revocado |
| 403 | `FORBIDDEN` | Rol sin permiso (salvo el caso de 404 de la sección 2.3) |
| 404 | `NOT_FOUND`, `PAIRING_CODE_INVALID` | No existe o no es accesible para ese usuario |
| 409 | `EMAIL_TAKEN`, `RECORD_CONFLICT`, `LAST_ADMIN` | Conflictos |
| 410 | `PAIRING_CODE_EXPIRED` | Código caducado o usado |
| 413 | `PAYLOAD_TOO_LARGE` | Sobre de más de 256 KB |
| 422 | `VALIDATION_ERROR`, `CONSENT_REQUIRED` | Esquema o consentimiento |
| 423 | `ACCOUNT_DISABLED` | Cuenta desactivada |
| 429 | `RATE_LIMITED` | Demasiados intentos (inicio de sesión, registro, emparejamiento) |
| 500 | `SERVER_ERROR` | Error interno, sin detalles técnicos en la respuesta |
| 503 | `STORAGE_UNAVAILABLE` | **v1.1.0.** La base de datos no respondió. Nada quedó guardado a medias. Cabecera `Retry-After` (segundos) |

Los textos visibles de los errores en la web y en el visor son claves de texto y pasan por la aprobación de Sara.

---

## 9. Otras rutas

| Ruta | Descripción |
|---|---|
| `GET /health` | `200 { "status": "ok", "version": "…" }`. Sin datos. No toca la base. |
| `GET /health/ready` | **v1.1.0.** `200 { "status": "ok", "version", "database": "ok" }` si el servidor llega a PostgreSQL; `503 STORAGE_UNAVAILABLE` si no. |
| `GET /public/product-info` | **v1.1.0.** Caso de uso «Visualizar información del producto», sin sesión: `{ "name", "tagline", "description", "audience", "features[]", "howItWorks[]", "requirements", "disclaimer", "contentVersion", "contentStatus", "apiVersion" }`. `contentStatus: "pendiente_de_aprobacion"` hasta que Sara apruebe el texto. La web puede seguir usando su contenido estático. |

---

## 10. Cambios que esto supone en la app Unity actual

| Hoy (`FastAPIClient`) | Con el contrato v1 |
|---|---|
| `POST /api/session/start`, `/metrics`, `/end` sin reintentos | `POST /api/v1/device/records` desde la bandeja de salida, idempotente |
| `GET /api/session/command/{sessionId}` cada 5 s | Se retira (D13 de R1). `GET /device/context` solo en el Refugio |
| Sin autenticación | Token de dispositivo tras emparejar |
| `LevelMetrics` | `level_record` v1; las métricas actuales van en `extra` |
| `proximityMin = -1` | `minDistanceM = null` |
| HTTP en todas las builds | HTTPS en la build de entrega |

---

## 11. Pruebas de contrato

- **Backend (pytest):** cada ruta con su caso válido, sus errores de la tabla 8 y la matriz de roles de la sección 2.3 completa (incluido el 404 entre profesionales). Idempotencia de `/device/records` (mismo sobre dos veces → `duplicate`; mismo `recordId` con otro contenido → `409`). Los registros desordenados se enlazan bien. Ningún log contiene correos, nombres ni tokens.
- **Web:** tipos generados desde `openapi.json`; pruebas con un servidor simulado que devuelve los ejemplos de este documento.
- **Unity:** pruebas EditMode de la bandeja con un servidor simulado (`tools/`) que devuelve `201`, `200 duplicate`, `409`, `422`, `401`, `429` y `500`.
- Los ejemplos JSON de este documento se guardan como archivos en `docs/api/examples/` y la app VR, el backend y la web los usan en sus pruebas.

---

## 12. Cambios de `contrato-v1.1.0` (04-11-2026)

**Aprobada por Sara el 09-11-2026.** En la misma versión se completa la sección 3 (modelo de datos) para que coincida con `app/db/models.py`: tablas `pairing_codes`, `inbound_records` y `rate_limit_events`, columnas que faltaban y relaciones sin clave foránea (3.3). Es documentación: no cambia ninguna ruta ni tabla.

Motivo: implementar los diagramas UML/BPMN (casos de uso, secuencias de terapia y del profesional, BPMN de inicio de sesión y terapia, contexto nivel 0 y despliegue). Matriz completa en `NP_Coordinacion/informes/BACK_MATRIZ_DIAGRAMAS_2026-11-04.md`.

**Compatibilidad:** ninguna ruta v1 cambia de método, ruta ni campos obligatorios. Solo se añaden rutas y campos de respuesta. La app Unity v1 sigue funcionando sin cambios.

| Tipo | Ruta | Diagrama |
|---|---|---|
| Nueva | `GET /public/product-info` | Caso de uso «Visualizar información del producto» |
| Nueva | `GET /health/ready` | Despliegue: Interfaz BD ⇄ PostgreSQL |
| Nueva | `GET /me/therapy` | Caso de uso «Iniciar terapia»; contexto «Iniciar y finalizar terapia» |
| Nueva | `PUT /me/phobia-grade`, `PUT /device/phobia-grade` | BPMN «Ajustar grado de fobia» |
| Nueva | `GET /device/sessions/{sessionId}` | Secuencia terapia «Retroalimentación guardada» |
| Nueva | `POST /device/unpair` | Contexto «Iniciar y cerrar sesión» (visor) |
| Nueva | `GET /patients/{patientId}/feedback` | Secuencia profesional «Consultar retroalimentación» |
| Nueva | `GET /admin/users/{userId}`, `PUT /admin/users/{userId}/password` | Caso de uso «Gestionar perfiles» |
| Ampliada | `PATCH /admin/users/{userId}` (+`fullName`, `email`) | «Gestionar perfiles» |
| Ampliada | `GET /device/context` (+`phobiaGrade`, `phobiaGradeUpdatedAt`) | BPMN «Ajustar grado de fobia» |
| Ampliada | `POST /device/records` (+`session`, `feedback`; `503 STORAGE_UNAVAILABLE`) | Secuencia terapia; BPMN «¿Almacena datos?» |
| Ampliada | `POST /patients/{patientId}/notes` (respuesta con la nota completa) | Secuencia profesional «Comentario anotado» |
| Ampliada | `GET /patients/{patientId}/notes` (`?sessionId=`) | Contexto «Consultar notas agregadas» |
| Ampliada | `GET /patients` (+`phobiaGrade`) | «Gestionar avance» |

Esquema: columnas `clinical.patients.phobia_grade` (1–5, nula) y `phobia_grade_updated_at` (migración Alembic `0003`). Versión del servicio: `0.2.0`.
Ejemplos nuevos en `docs/api/examples/`: `product_info.response.200.json`, `phobia_grade.*`, `me_therapy.response.200.json`, `device_context.v1_1.response.200.json`, `device_session.response.200.json`, `records_session_start.response.201.json`, `records_session_end.response.201.json`, `feedback.response.200.json`, `note.response.201.json` (ampliado), `admin_user_patch.request.json`, `admin_password_reset.request.json`, `health_ready.response.200.json`, `error.storage_unavailable.503.json`.
