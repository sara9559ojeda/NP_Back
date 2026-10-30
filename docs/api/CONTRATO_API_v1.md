# Contrato de la API v1 — NEUROPHOBIA

- **Versión:** `contrato-v1.0.0`, aprobada por Sara María Ojeda López el 30-10-2026. Cualquier cambio necesita una nueva aprobación y una versión nueva. **Este repositorio (NP_Back) es la fuente del contrato.**
- **Fecha:** 30-10-2026
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
| `/me` (datos propios) | — | ✅ | ✅ | ✅ |
| Códigos de emparejamiento | — | ✅ propios | ✅ de sus pacientes | — |
| `/device/*` (visor) | — | ✅ con token de dispositivo | — | — |
| Progreso y sesiones de un paciente | — | ✅ solo los propios | ✅ solo sus pacientes asignados | ❌ (ver nota) |
| Notas | — | ❌ | ✅ de sus pacientes | ❌ |
| Plan del paciente (nivel inicial permitido) | — | ❌ | ✅ de sus pacientes | — |
| Usuarios, roles, asignaciones | — | — | — | ✅ |
| Exportación anónima para análisis | — | — | — | ✅ |

> **Nota:** el administrador gestiona perfiles, pero **no** ve datos clínicos (minimización, Ley 1581). Si el asesor prefiere otra cosa, se cambia en D21.
> Si un profesional pide un paciente que no es suyo, la respuesta es **404**, no 403, para no revelar que existe.

---

## 3. Modelo de datos (resumen)

Separación de identidad y datos clínicos (D15 de R1):

```
esquema identity                          esquema clinical
───────────────                           ────────────────
users(id, email, password_hash,           patients(pseudonym_id, allowed_start_level,
      role, active, created_at)                    created_at)
personal_data(user_id, full_name, …)      devices(id, pseudonym_id, model, app_version,
consents(id, user_id, consent_version,             paired_at, revoked_at, token_hash)
         granted_at, withdrawn_at)        sessions(id, pseudonym_id, device_id, started_at,
identity_links(user_id, pseudonym_id)  ◄──         ended_at, phobia_grade, test_session,
assignments(professional_user_id,                  end_reason, level_reached, raw JSONB)
            patient_user_id, active)      level_records(id, session_id, level, attempt,
refresh_tokens(...)                                outcome, payload JSONB)
                                          analyses(session_id, method, method_version,
                                                   tolerance_index, recommendation,
                                                   basis JSONB, created_at)
                                          notes(id, pseudonym_id, session_id NULL,
                                                author_user_id, text, created_at, edited_at)
```

- Solo la capa de servicio une `identity` y `clinical` a través de `identity_links`.
- Los registros del visor se guardan completos en `JSONB` (`raw`, `payload`) y, además, en columnas los campos que se consultan.
- **Retirar el consentimiento** borra `personal_data` e `identity_links`, desactiva la cuenta y deja los datos clínicos sin vínculo (anónimos). El plazo de conservación está pendiente (D23).

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
| `PATCH /admin/users/{userId}` | `{ "role"?, "active"? }` → `200`. `409 LAST_ADMIN` si se quita el último admin. |
| `GET /admin/assignments?professionalId=` | Asignaciones profesional–paciente. |
| `POST /admin/assignments` | `{ "professionalId", "patientId" }` → `201` |
| `DELETE /admin/assignments/{assignmentId}` | `204` |
| `GET /admin/exports/analysis-dataset` | Exportación **anónima**: sin `pseudonym_id`, con identificadores nuevos en cada exportación; excluye `testSession = true`. JSON o CSV (`Accept`). |

---

## 5. Rutas: seguimiento (web)

### 5.1 Profesional (HU-12, HU-13, RQF014, RQF015)

| Ruta | Descripción |
|---|---|
| `GET /patients` | Pacientes asignados: `{ "patientId", "fullName", "lastSessionAt", "levelReached", "lastRecommendation" }`. |
| `GET /patients/{patientId}/progress` | Igual que `GET /me/progress`, para ese paciente. |
| `GET /patients/{patientId}/sessions` | Lista paginada de sesiones. |
| `GET /patients/{patientId}/sessions/{sessionId}` | Detalle: sesión, registros por nivel, SUDS y análisis. |
| `PUT /patients/{patientId}/plan` | `{ "allowedStartLevel": 1–5 }`. Nivel inicial permitido (HU-08, RQF009). Por defecto, 1. |
| `GET /patients/{patientId}/notes` | Notas paginadas, más recientes primero. |
| `POST /patients/{patientId}/notes` | `{ "text", "sessionId"? }` → `201 { "noteId", "createdAt" }`. |
| `PATCH /patients/{patientId}/notes/{noteId}` | Solo el autor. Guarda `editedAt`. |

### 5.2 Paciente (HU-05, RQF013)

| Ruta | Descripción |
|---|---|
| `GET /me/progress` | `{ "sessionsCount", "levelReached", "lastSessions": [ { "sessionId", "startedAt", "levelReached", "totalDurationSeconds", "recommendation" } ] }` |
| `GET /me/sessions` y `GET /me/sessions/{sessionId}` | Igual que en el profesional, sin notas. |

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

Los textos visibles de los errores en la web y en el visor son claves de texto y pasan por la aprobación de Sara.

---

## 9. Otras rutas

| Ruta | Descripción |
|---|---|
| `GET /health` | `200 { "status": "ok", "version": "…" }`. Sin datos. |
| Página pública (HU-14, RQF002) | Es contenido estático de la web; no necesita API. Su texto (incluido el aviso de que no sustituye un tratamiento) pasa por la aprobación de Sara. |

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
