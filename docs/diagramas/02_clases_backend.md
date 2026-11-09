# Diagrama de clases — Backend (NP_Back)

Fuente: `app/`. El backend es Python. Las clases reales son los modelos ORM, las *dataclasses* de IA y algunas de `core`. Los **servicios** y **repositorios** son módulos de funciones; en UML se dibujan como clases con estereotipo `«service»` / `«repository»` y operaciones estáticas, que es la convención habitual.

Para no saturar, se puede dividir en dos hojas de VP Online:

- **Hoja A:** dominio, con las entidades del ORM. Es la sección 1.
- **Hoja B:** lógica, con servicios, repositorios, IA y core. Son las secciones 2 a 5.

Se omite el parámetro `db : Session` de todas las operaciones, porque lo llevan todas.

---

## 1. Entidades (paquete `app.db.models`)

Estereotipo `«entity»` en todas. Todas heredan de **Base** (`DeclarativeBase`), y la relación se dibuja como *Generalization* hacia `Base`.

| Clase | Atributos |
|---|---|
| **User** (`identity.users`) | `+ id : UUID` · `+ email : str` · `+ password_hash : str [0..1]` · `+ role : str` · `+ active : bool` · `+ created_at : datetime` · `+ updated_at : datetime [0..1]` · `+ withdrawn_at : datetime [0..1]` |
| **PersonalData** | `+ user_id : UUID` · `+ full_name : str` · `+ updated_at : datetime` |
| **Consent** | `+ id : UUID` · `+ user_id : UUID` · `+ consent_version : str` · `+ granted_at : datetime` · `+ withdrawn_at : datetime [0..1]` |
| **IdentityLink** | `+ user_id : UUID` · `+ pseudonym_id : UUID` |
| **Assignment** | `+ id : UUID` · `+ professional_user_id : UUID` · `+ patient_user_id : UUID` · `+ active : bool` · `+ created_at : datetime` · `+ ended_at : datetime [0..1]` |
| **RefreshToken** | `+ id : UUID` · `+ user_id : UUID` · `+ family_id : UUID` · `+ token_hash : str` · `+ created_at : datetime` · `+ expires_at : datetime` · `+ revoked_at : datetime [0..1]` |
| **RateLimitEvent** | `+ id : int` · `+ key_hash : str` · `+ occurred_at : datetime` |
| **Patient** (`clinical.patients`) | `+ pseudonym_id : UUID` · `+ allowed_start_level : int` · `+ plan_updated_at : datetime [0..1]` · `+ phobia_grade : int [0..1]` · `+ phobia_grade_updated_at : datetime [0..1]` · `+ retain_until : datetime [0..1]` · `+ created_at : datetime` |
| **PairingCode** | `+ id : UUID` · `+ pseudonym_id : UUID` · `+ code_hash : str` · `+ created_at : datetime` · `+ expires_at : datetime` · `+ used_at : datetime [0..1]` |
| **Device** | `+ id : UUID` · `+ pseudonym_id : UUID` · `+ model : str` · `+ app_version : str` · `+ token_hash : str` · `+ paired_at : datetime` · `+ last_seen_at : datetime [0..1]` · `+ revoked_at : datetime [0..1]` |
| **TherapySession** (`clinical.sessions`) | `+ id : UUID` · `+ pseudonym_id : UUID` · `+ device_id : UUID [0..1]` · `+ has_start : bool` · `+ has_end : bool` · `+ started_at : datetime [0..1]` · `+ ended_at : datetime [0..1]` · `+ phobia_grade : int [0..1]` · `+ test_session : bool [0..1]` · `+ app_version : str [0..1]` · `+ device_model : str [0..1]` · `+ end_reason : str [0..1]` · `+ level_reached : int [0..1]` · `+ total_duration_seconds : float [0..1]` · `+ raw : dict` · `+ created_at : datetime` |
| **LevelRecord** | `+ id : UUID` · `+ session_id : UUID` · `+ level : int` · `+ attempt : int` · `+ outcome : str` · `+ criterion_met : bool` · `+ started_at : datetime` · `+ ended_at : datetime` · `+ permanence_seconds : float` · `+ min_distance_m : float [0..1]` · `+ avoidance_count : int` · `+ payload : dict` · `+ received_at : datetime` |
| **Analysis** | `+ session_id : UUID` · `+ method : str` · `+ method_version : str` · `+ tolerance_index : float` · `+ recommendation : str` · `+ basis : list` · `+ clinical_status : str` · `+ created_at : datetime` |
| **Note** | `+ id : UUID` · `+ pseudonym_id : UUID` · `+ session_id : UUID [0..1]` · `+ author_user_id : UUID` · `+ text : str` · `+ created_at : datetime` · `+ edited_at : datetime [0..1]` |
| **InboundRecord** | `+ record_id : UUID` · `+ pseudonym_id : UUID` · `+ device_id : UUID [0..1]` · `+ session_id : UUID` · `+ type : str` · `+ schema_version : int` · `+ content_hash : str` · `+ received_at : datetime` |

### Asociaciones entre entidades

| De | A | Tipo | Multiplicidad (de — a) |
|---|---|---|---|
| User | PersonalData | Composition (rombo en User) | 1 — 0..1 |
| User | Consent | Composition | 1 — 0..* |
| User | IdentityLink | Composition | 1 — 0..1 |
| User | RefreshToken | Composition | 1 — 0..* |
| User | Assignment | Association, rol `professional` | 1 — 0..* |
| User | Assignment | Association, rol `patient` | 1 — 0..* |
| IdentityLink | Patient | Association **punteada** `«logical»` | 0..1 — 1 |
| Patient | PairingCode | Composition | 1 — 0..* |
| Patient | Device | Composition | 1 — 0..* |
| Patient | TherapySession | Composition | 1 — 0..* |
| Patient | Note | Composition | 1 — 0..* |
| Device | TherapySession | Association | 0..1 — 0..* |
| TherapySession | LevelRecord | Composition | 1 — 0..* |
| TherapySession | Analysis | Composition | 1 — 0..* |
| TherapySession | Note | Association | 0..1 — 0..* |
| User | Note | Association **punteada** `«logical»`, rol `author` | 1 — 0..* |
| InboundRecord | TherapySession | Association **punteada** `«logical»` | 0..* — 1 |

---

## 2. Servicios (paquete `app.services`) — estereotipo `«service»`

| Clase | Operaciones |
|---|---|
| **AuthService** (`auth.py`) | `+ register(data : RegisterIn, client_ip : str) : UUID` · `+ login(email : str, password : str, client_ip : str) : IssuedTokens` · `+ refresh(refresh_token : str) : IssuedTokens` · `+ logout(refresh_token : str) : void` · `+ create_account(email, password, role, full_name) : UUID` · `+ ensure_patient_link(user_id : UUID) : UUID` · `- _issue(user_id, role, family_id) : IssuedTokens` |
| **AccountsService** (`accounts.py`) | `+ get_me(actor : Actor) : MeOut` · `+ patch_me(actor : Actor, data : MePatch) : MeOut` · `+ change_password(actor : Actor, current : str, new : str) : void` · `+ withdraw_consent(actor : Actor) : void` · `+ change_email(user : User, email : str, now : datetime) : void` · `+ commit_profile() : void` |
| **AdminService** (`admin.py`) | `+ list_users(page, role, active, q) : AdminUserPage` · `+ get_user(user_id) : AdminUserOut` · `+ create_user(data : AdminUserCreate) : AdminUserOut` · `+ patch_user(user_id, data : AdminUserPatch) : AdminUserOut` · `+ reset_password(user_id, temporary_password) : void` · `+ list_assignments(page, professional_id) : AssignmentPage` · `+ create_assignment(professional_id, patient_id) : AssignmentOut` · `+ delete_assignment(assignment_id) : void` · `+ analysis_dataset() : dict` · `+ dataset_to_csv(dataset : dict) : str` |
| **PairingService** (`pairing.py`) | `+ create_code(pseudonym : UUID) : PairingCodeOut` · `+ pair(data : PairIn, client_ip : str) : PairOut` · `+ authenticate_device(token : str) : DeviceActor` · `+ list_devices(pseudonym) : DevicePage` · `+ revoke_device(pseudonym, device_id) : void` |
| **RecordsService** (`records.py`) | `+ ingest(device : DeviceActor, body : dict) : RecordResult` · `+ parse_envelope(body) : RecordEnvelope` · `+ content_hash(body : dict) : str` · `+ device_context(device : DeviceActor) : DeviceContext` · `- _store(...) : str` · `- _duplicate_or_conflict(...) : str` |
| **TrackingService** (`tracking.py`) | `+ own_pseudonym(actor : Actor) : UUID` · `+ assigned_pseudonym(actor : Actor, patient_id : UUID) : UUID` · `+ progress(pseudonym) : ProgressOut` · `+ list_sessions(pseudonym, page) : SessionPage` · `+ session_detail(pseudonym, session_id, with_notes : bool) : SessionDetail` · `+ my_patients(actor, page) : PatientPage` · `+ set_plan(patient_id, pseudonym, level : int) : PlanOut` · `+ list_notes(pseudonym, page, session_id) : NotePage` · `+ add_note(actor, pseudonym, text, session_id) : NoteCreated` · `+ edit_note(actor, pseudonym, note_id, text) : NoteOut` · `+ session_status(s : TherapySession) : str` · `+ analysis_out(a : Analysis) : AnalysisOut` |
| **TherapyService** (`therapy.py`) | `+ set_phobia_grade(pseudonym, grade : int) : PhobiaGradeOut` · `+ sync_phobia_grade_from_session(pseudonym, grade, at) : void` · `+ therapy_state(pseudonym) : TherapyStateOut` · `+ device_session(device : DeviceActor, session_id) : DeviceSessionOut` · `+ feedback_page(pseudonym, page) : FeedbackPage` · `+ unpair(device : DeviceActor) : void` · `+ session_ref(s : TherapySession) : SessionRef` |
| **AnalysisService** (`analysis.py`) | `+ refresh_analysis(session : TherapySession) : void` · `+ feedback_for(session : TherapySession) : FeedbackOut` |

Clases de valor del paquete (`«dataclass»`):

- **Actor:** `+ user_id : UUID` · `+ role : str`
- **DeviceActor:** `+ device_id : UUID` · `+ pseudonym_id : UUID`
- **IssuedTokens:** `+ access_token : str` · `+ expires_in : int` · `+ refresh_token : str` · `+ user_id : UUID` · `+ role : str`

## 3. Repositorios (paquete `app.repositories`) — estereotipo `«repository»`

- **IdentityRepository** (`identity.py`). Opera sobre User, PersonalData, Consent, IdentityLink, Assignment y RefreshToken.
  - `+ get_user(user_id) : User`
  - `+ get_user_by_email(email) : User`
  - `+ email_exists(email) : bool`
  - `+ add_user(...) : User`
  - `+ set_full_name(user_id, full_name)`
  - `+ delete_personal_data(user_id)`
  - `+ add_consent(user_id, version)`
  - `+ withdraw_consents(user_id, now)`
  - `+ get_pseudonym(user_id) : UUID`
  - `+ get_user_id_for_pseudonym(pseudonym_id) : UUID`
  - `+ add_link(user_id, pseudonym_id)`
  - `+ delete_link(user_id)`
  - `+ list_users(...) : list`
  - `+ count_active_admins() : int`
  - `+ add_assignment(professional_id, patient_id)`
  - `+ list_assignments(page, professional_id)`
  - `+ end_assignments_of(user_id, now)`
  - `+ is_assigned(professional_id, patient_id) : bool`
  - `+ add_refresh_token(...)`
  - `+ get_refresh_token(token_hash)`
  - `+ revoke_family(family_id, now)`
  - `+ revoke_user_tokens(user_id, now)`
- **ClinicalRepository** (`clinical.py`). Opera sobre Patient, PairingCode, Device, TherapySession, LevelRecord, Analysis, Note e InboundRecord.
  - `+ add_patient() : Patient`
  - `+ get_patient(pseudonym_id) : Patient`
  - `+ add_pairing_code(...)`
  - `+ get_pairing_code(code_hash)`
  - `+ invalidate_pairing_codes(pseudonym_id)`
  - `+ add_device(...)`
  - `+ get_device_by_token_hash(token_hash)`
  - `+ list_devices(pseudonym_id)`
  - `+ revoke_devices(pseudonym_id, now)`
  - `+ try_add_inbound(...)`
  - `+ get_inbound(record_id)`
  - `+ lock_or_create_session(session_id, pseudonym_id)`
  - `+ get_session(pseudonym_id, session_id)`
  - `+ list_sessions(pseudonym_id, page)`
  - `+ progress_sessions(pseudonym_id)`
  - `+ add_level_record(record)`
  - `+ level_records(session_id)`
  - `+ upsert_analysis(values)`
  - `+ analyses_for(session_ids, method)`
  - `+ add_note(...)`
  - `+ get_note(...)`
  - `+ list_notes(...)`
  - `+ open_session(pseudonym_id)`
  - `+ feedback_sessions(pseudonym_id, method)`
  - `+ export_rows(method)`

## 4. IA (paquete `app.ai`)

| Clase | Estereotipo | Miembros |
|---|---|---|
| **SessionAnalyzer** | `«interface»` (Protocol) | `+ method : str` · `+ method_version : str` · `+ analyze(features : SessionFeatures) : AnalysisResult [0..1]` |
| **RulesBaselineAnalyzer** | — | `- config : dict` · `+ __init__(config : dict)` · `+ analyze(features : SessionFeatures) : AnalysisResult [0..1]` · `- _effect(score : float) : Effect` |
| **SessionFeatures** | `«dataclass»` | `+ phobia_grade : int [0..1]` · `+ level_reached : int [0..1]` · `+ end_reason : str [0..1]` · `+ levels : LevelFeatures [*]` |
| **LevelFeatures** | `«dataclass»` | `+ level : int` · `+ attempt : int` · `+ outcome : str` · `+ criterion_met : bool` · `+ permanence_seconds : float` · `+ avoidance_count : int` · `+ min_distance_m : float [0..1]` · `+ suds_before : int [0..1]` · `+ suds_after : int [0..1]` · `+ ended_at_epoch : float` |
| **AnalysisResult** | `«dataclass»` | `+ method : str` · `+ method_version : str` · `+ tolerance_index : float` · `+ recommendation : Recommendation` · `+ basis : BasisItem [*]` · `+ clinical_status : str = "pendiente_de_validar"` |
| **BasisItem** | `«dataclass»` | `+ feature : str` · `+ value : float` · `+ effect : Effect` |
| **Recommendation** | `«enumeration»` | `advance` · `repeat` · `step_back` |
| **Effect** | `«enumeration»` | `favorable` · `unfavorable` · `neutral` |
| **AnalyzerRegistry** (`registry.py`) | `«utility»` | `+ get_analyzer(method : str) : SessionAnalyzer` |
| **FeatureExtractor** (`features.py`) | `«utility»` | `+ level_features(payload : dict) : LevelFeatures` · `+ session_features(phobia_grade, level_reached, end_reason, level_payloads) : SessionFeatures` |

## 5. Core (paquete `app.core`)

| Clase | Miembros |
|---|---|
| **Settings** (`BaseSettings`) | `+ database_url : SecretStr` · `+ secret_key : SecretStr` · `+ cors_origin : str` · `+ cookie_secure : bool` · `+ access_token_minutes : int = 15` · `+ refresh_token_days : int = 7` · `+ pairing_code_minutes : int = 10` · `+ pairing_max_failures : int = 5` · `+ max_record_bytes : int` · `+ progress_last_sessions : int = 5` · `+ ai_method : str = "rules-baseline"` · `+ log_level : str` |
| **ApiError** (`Exception`) | `+ status : int` · `+ code : str` · `+ detail : str [0..1]` · `+ errors : list [0..1]` · `+ headers : dict [0..1]` |
| **Page** | `+ limit : int` · `+ after : (datetime, UUID) [0..1]` |
| **SlidingWindowLimiter** | `+ count(key, window) : int` · `+ hit(key, window)` · `+ check_and_hit(key, limit, window)` · `+ ensure_below(key, limit, window)` · `+ reset()` |
| **PostgresWindowLimiter** | Las mismas operaciones que SlidingWindowLimiter, guardadas en `RateLimitEvent`. |
| **RedactingFilter** (`logging.Filter`) | `+ filter(record) : bool` |
| **AccessLogMiddleware** | `+ __call__(scope, receive, send)` |
| **TokenExpired**, **TokenInvalid** | Excepciones (`Exception`). |

---

## Relaciones de la hoja B

| De | A | Tipo |
|---|---|---|
| RulesBaselineAnalyzer | SessionAnalyzer | **Realization** |
| SessionFeatures | LevelFeatures | Composition 1 — 0..* |
| AnalysisResult | BasisItem | Composition 1 — 0..* |
| AnalysisResult | Recommendation | Association (atributo) |
| BasisItem | Effect | Association (atributo) |
| AnalyzerRegistry | SessionAnalyzer | Dependency `«create»` |
| AnalysisService | AnalyzerRegistry, FeatureExtractor, ClinicalRepository | Dependency `«use»` |
| RecordsService | AnalysisService, TherapyService, ClinicalRepository | Dependency `«use»` |
| AuthService | IdentityRepository, ClinicalRepository, PostgresWindowLimiter | Dependency `«use»` |
| AccountsService | IdentityRepository, ClinicalRepository | Dependency `«use»` |
| AdminService | AuthService, AccountsService, IdentityRepository, ClinicalRepository | Dependency `«use»` |
| PairingService | IdentityRepository, ClinicalRepository, PostgresWindowLimiter | Dependency `«use»` |
| TrackingService, TherapyService | ClinicalRepository (TrackingService también IdentityRepository) | Dependency `«use»` |
| IdentityRepository | User, PersonalData, Consent, IdentityLink, Assignment, RefreshToken | Dependency `«use»` |
| ClinicalRepository | Patient, PairingCode, Device, TherapySession, LevelRecord, Analysis, Note, InboundRecord | Dependency `«use»` |
| PostgresWindowLimiter | RateLimitEvent | Dependency `«use»` |
| Todos los servicios | ApiError | Dependency `«throw»` |
| PairingService, RecordsService, TherapyService | DeviceActor | Dependency `«use»` |
| AccountsService, TrackingService | Actor | Dependency `«use»` |
