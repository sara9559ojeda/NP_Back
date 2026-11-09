# Diagrama entidad-relación

Fuente: `app/db/models.py` y las migraciones `alembic/versions/0001`–`0003`. Base de datos PostgreSQL con dos esquemas.

En VP Online crea dos *Package* llamados **identity** y **clinical** y pon cada tabla en el suyo.

Leyenda: **PK** = clave primaria · **FK** = clave foránea · **U** = única · **N** = admite nulos (si no pone N, es NOT NULL).

---

## Esquema `identity`

### users
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| id | uuid | PK | | |
| email | varchar(320) | U | | |
| password_hash | text | | N | |
| role | varchar(16) | | | CHECK `role IN ('patient','professional','admin')` |
| active | boolean | | | por defecto `true` |
| created_at | timestamptz | | | por defecto `now()` |
| updated_at | timestamptz | | N | |
| withdrawn_at | timestamptz | | N | fecha en que se retiró el consentimiento |

### personal_data
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| user_id | uuid | PK, FK → users.id | |
| full_name | varchar(200) | | |
| updated_at | timestamptz | | |

### consents
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | uuid | PK | |
| user_id | uuid | FK → users.id | |
| consent_version | varchar(64) | | |
| granted_at | timestamptz | | |
| withdrawn_at | timestamptz | | N |

### identity_links
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| user_id | uuid | PK, FK → users.id | | |
| pseudonym_id | uuid | U | | apunta a `clinical.patients` **sin FK** (relación lógica) |

### assignments
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| id | uuid | PK | | |
| professional_user_id | uuid | FK → users.id | | |
| patient_user_id | uuid | FK → users.id | | |
| active | boolean | | | |
| created_at | timestamptz | | | |
| ended_at | timestamptz | | N | |

Índice único parcial `(professional_user_id, patient_user_id) WHERE active`.

### refresh_tokens
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | uuid | PK | |
| user_id | uuid | FK → users.id | |
| family_id | uuid | | |
| token_hash | varchar(64) | U | |
| created_at | timestamptz | | |
| expires_at | timestamptz | | |
| revoked_at | timestamptz | | N |

### rate_limit_events
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | bigint (identity) | PK | |
| key_hash | varchar(64) | | |
| occurred_at | timestamptz | | |

Tabla técnica sin relaciones; se dibuja aislada.

---

## Esquema `clinical`

### patients
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| pseudonym_id | uuid | PK | | |
| allowed_start_level | smallint | | | CHECK 1–5, por defecto 1 |
| plan_updated_at | timestamptz | | N | |
| phobia_grade | smallint | | N | CHECK 1–5 |
| phobia_grade_updated_at | timestamptz | | N | |
| retain_until | timestamptz | | N | preparado para D23, sin uso |
| created_at | timestamptz | | | |

### pairing_codes
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | uuid | PK | |
| pseudonym_id | uuid | FK → patients.pseudonym_id | |
| code_hash | varchar(64) | U | |
| created_at | timestamptz | | |
| expires_at | timestamptz | | |
| used_at | timestamptz | | N |

### devices
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | uuid | PK | |
| pseudonym_id | uuid | FK → patients.pseudonym_id | |
| model | varchar(32) | | |
| app_version | varchar(32) | | |
| token_hash | varchar(64) | U | |
| paired_at | timestamptz | | |
| last_seen_at | timestamptz | | N |
| revoked_at | timestamptz | | N |

### sessions
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| id | uuid | PK | | lo genera el visor |
| pseudonym_id | uuid | FK → patients.pseudonym_id | | |
| device_id | uuid | FK → devices.id | N | ON DELETE SET NULL |
| has_start | boolean | | | |
| has_end | boolean | | | |
| started_at | timestamptz | | N | |
| ended_at | timestamptz | | N | |
| phobia_grade | smallint | | N | CHECK 1–5 |
| test_session | boolean | | N | |
| app_version | varchar(32) | | N | |
| device_model | varchar(32) | | N | |
| end_reason | varchar(32) | | N | |
| level_reached | smallint | | N | |
| total_duration_seconds | float | | N | |
| raw | jsonb | | | |
| created_at | timestamptz | | | |

### level_records
| Columna | Tipo | Clave | Nulo |
|---|---|---|---|
| id | uuid | PK | |
| session_id | uuid | FK → sessions.id | |
| level | smallint | | |
| attempt | smallint | | |
| outcome | varchar(32) | | |
| criterion_met | boolean | | |
| started_at | timestamptz | | |
| ended_at | timestamptz | | |
| permanence_seconds | float | | |
| min_distance_m | float | | N |
| avoidance_count | integer | | |
| payload | jsonb | | |
| received_at | timestamptz | | |

### analyses
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| session_id | uuid | PK, FK → sessions.id | | PK compuesta |
| method | varchar(32) | PK | | PK compuesta |
| method_version | varchar(16) | | | |
| tolerance_index | float | | | CHECK 0–1 |
| recommendation | varchar(16) | | | CHECK `advance`, `repeat`, `step_back` |
| basis | jsonb | | | |
| clinical_status | varchar(32) | | | |
| created_at | timestamptz | | | |

### notes
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| id | uuid | PK | | |
| pseudonym_id | uuid | FK → patients.pseudonym_id | | |
| session_id | uuid | FK → sessions.id | N | ON DELETE SET NULL |
| author_user_id | uuid | | | apunta a `identity.users` **sin FK** (relación lógica) |
| text | text | | | |
| created_at | timestamptz | | | |
| edited_at | timestamptz | | N | |

### inbound_records
| Columna | Tipo | Clave | Nulo | Notas |
|---|---|---|---|---|
| record_id | uuid | PK | | garantiza idempotencia |
| pseudonym_id | uuid | | | sin FK |
| device_id | uuid | | N | sin FK |
| session_id | uuid | | | sin FK (indexada) |
| type | varchar(16) | | | `session_start`, `level_record`, `session_end` |
| schema_version | smallint | | | |
| content_hash | varchar(64) | | | |
| received_at | timestamptz | | | |

---

## Relaciones

Las relaciones **con FK** se dibujan con línea continua. Todas son ON DELETE CASCADE salvo las indicadas.

| # | Desde (1) | Hacia (N) | Cardinalidad | Columna FK |
|---|---|---|---|---|
| R1 | users | personal_data | 1 : 0..1 | personal_data.user_id |
| R2 | users | consents | 1 : 0..N | consents.user_id |
| R3 | users | identity_links | 1 : 0..1 | identity_links.user_id |
| R4 | users (profesional) | assignments | 1 : 0..N | assignments.professional_user_id |
| R5 | users (paciente) | assignments | 1 : 0..N | assignments.patient_user_id |
| R6 | users | refresh_tokens | 1 : 0..N | refresh_tokens.user_id |
| R7 | patients | pairing_codes | 1 : 0..N | pairing_codes.pseudonym_id |
| R8 | patients | devices | 1 : 0..N | devices.pseudonym_id |
| R9 | patients | sessions | 1 : 0..N | sessions.pseudonym_id |
| R10 | devices | sessions | 0..1 : 0..N | sessions.device_id (SET NULL) |
| R11 | sessions | level_records | 1 : 0..N | level_records.session_id |
| R12 | sessions | analyses | 1 : 0..N | analyses.session_id (una fila por método) |
| R13 | patients | notes | 1 : 0..N | notes.pseudonym_id |
| R14 | sessions | notes | 0..1 : 0..N | notes.session_id (SET NULL) |

Las relaciones **lógicas, sin FK**, se dibujan con línea punteada y una nota *«sin FK: une la capa de servicio»*:

| # | Desde | Hacia | Cardinalidad | Columna |
|---|---|---|---|---|
| L1 | identity_links | patients | 0..1 : 1 | identity_links.pseudonym_id ↔ patients.pseudonym_id |
| L2 | users (profesional) | notes | 1 : 0..N | notes.author_user_id |
| L3 | sessions | inbound_records | 1 : 0..N | inbound_records.session_id |

Al retirar el consentimiento se borran `personal_data` e `identity_links`: los datos clínicos quedan anónimos. La relación L1 es la única que une las dos personas lógicas. Conviene ponerla como nota en el diagrama.
