# Diagrama de clases — App VR (NPdefdef, Unity)

Fuente: `Assets/Scripts/` y `Assets/NeuroPhobia_*/Scripts/Runtime/` del repositorio NPdefdef. Son unas 107 clases propias. Aquí van las del **núcleo**: control de sesión, comunicación con el backend, métricas, estímulo y un controlador por nivel. Los HUD, efectos visuales y ajustes por nivel se resumen en la sección 6. Si hace falta, se pueden añadir con el mismo formato.

Todas las clases que heredan de `MonoBehaviour` se dibujan con *Generalization* hacia una clase **MonoBehaviour** marcada `«library» UnityEngine`. Así basta con dibujar `MonoBehaviour` una sola vez.

---

## 1. Control (paquete `Control`)

| Clase | Estereotipo | Atributos | Operaciones |
|---|---|---|---|
| **SessionManager** : MonoBehaviour | `«singleton»` | `+ Instance : SessionManager {static}` · `+ SessionId : string` · `+ CurrentLevel : int` · `+ PhobiaGrade : int` · `- report : SessionReport` · `- levelRetries : Dictionary<int,int>` · `- currentAttemptMetrics : Dictionary<int,LevelMetrics>` · `- beforeSuds : Dictionary<int,SudsEntry>` · `- pendingPost : LevelMetrics` · `- sessionStartTime : float` · `- ended : bool` · `- apiClient : FastAPIClient` | `+ StartSession(phobiaGrade : int, testSession : bool)` · `+ RegisterLevelRetry(level : int)` · `+ LevelRetries(level : int) : int` · `+ CurrentAttempt(level : int) : int` · `+ CurrentAttemptMetrics(level : int) : LevelMetrics` · `+ AddLevelMetrics(metrics : LevelMetrics)` · `+ RecordSudsBefore(level : int, value : int)` · `+ AwaitingSudsAfter(level : int) : bool` · `+ RecordSudsAfter(level : int, value : int)` · `+ PostPendingLevel()` · `+ EndSession(endReason : string)` · `+ GetReport() : SessionReport` · `+ ResolveInitialLevel(phobiaGrade : int) : int` |
| **LevelManager** : MonoBehaviour | `«singleton»` | `+ Instance : LevelManager {static}` | `+ LoadLevel(level : int)` · `+ UnlockNextLevel()` · `+ OnLevelComplete(level : int, metrics : LevelMetrics)` |
| **GameStateManager** : MonoBehaviour | — | `+ CurrentState : GameState {static}` · `+ OnStateChanged : event Action<GameState> {static}` | `+ SetState(state : GameState) {static}` |
| **GameState** | `«enumeration»` | `MENU` · `PLAYING` · `PAUSED` · `BREATHING` · `LEVEL_COMPLETE` · `SESSION_END` | |
| **LevelBootstrap** : MonoBehaviour | — | `- level : int = 1` · `- targetFrameRate : int = 72` | |
| **LevelCompletionTrigger** : MonoBehaviour | — | `- level : int` · `- completeLevel : bool` · `- playerTag : string` | |
| **XRBootstrap** : MonoBehaviour | `«internal»` | | Inicializa OpenXR al arrancar. |
| **AdaptiveCommandPoller** : MonoBehaviour | `«deprecated»` | `- pollingInterval : float` · `- pauseSeconds : float` | Retirado por D13; se desactiva en `Awake`. |

## 2. Comunicación (paquete `Comunicacion`)

| Clase | Estereotipo | Atributos | Operaciones |
|---|---|---|---|
| **FastAPIClient** : MonoBehaviour | — | `- baseUrl : string = "http://localhost:8000"` · `- timeoutSeconds : int = 10` · `- outbox : RecordOutbox` · `- cachedContext : DeviceContextDto` · `+ Context : DeviceContextDto` · `+ QuarantineCount : int` | `+ SetBaseUrl(url : string)` · `+ Pair(code : string, onDone : Action<bool,string>) : IEnumerator` · `+ Unpair(onDone : Action<bool>) : IEnumerator` · `+ RefreshContext(onDone : Action<DeviceContextDto>) : IEnumerator` · `+ PutPhobiaGrade(grade : int) : IEnumerator` · `+ AllowedStartLevel() : int` · `+ LastPhobiaGrade() : int` · `+ PostSessionStart(sessionId : string, phobiaGrade : int, testSession : bool) : IEnumerator` · `+ PostLevelMetrics(sessionId : string, level : int, metrics : LevelMetrics) : IEnumerator` · `+ PostSessionEnd(sessionId : string, report : SessionReport, endReason : string) : IEnumerator` · `+ SyncStatusText() : string` · `+ ApiRootFrom(url) : string {static}` · `+ Normalize(url) : string {static}` · `+ NormalizePairingCode(code) : string {static}` · `+ PairingError(status : long) : string {static}` |
| **DeviceRecordMapper** | `«utility»` (static) | | `+ NewId() : string` · `+ SessionStart(recordId, sessionId, startedUtc, phobiaGrade, ...) : string` · `+ LevelRecord(recordId, sessionId, metrics : LevelMetrics, attempt : int, endedUtc) : string` · `+ SessionEnd(recordId, sessionId, endedUtc, endReason, ...) : string` · `+ ResolveOutcome(metrics : LevelMetrics) : string` · `+ ResolveEndReason(report : SessionReport, requested : string) : string` · `+ LevelReached(report : SessionReport) : int` · `+ NormalizeDeviceModel(raw) : string` · `+ SafeVersion(raw) : string` |
| **RecordOutbox** | — (sealed) | `+ MinRetrySeconds : double = 2 {const}` · `+ MaxRetrySeconds : double = 300 {const}` · `+ Unpaired : string = "sin_vincular" {const}` · `+ OutboxDir : string` · `+ QuarantineDir : string` | `+ RecordOutbox(rootDirectory : string)` · `+ Enqueue(owner, type, recordId, json) : string` · `+ Pending(owner) : List<string>` · `+ PendingCount(owner) : int` · `+ Apply(path : string, action : OutboxAction)` · `+ Classify(httpStatus : long) : OutboxAction {static}` · `+ RetryDelaySeconds(failures : int, retryAfter : string) : double {static}` |
| **OutboxAction** | `«enumeration»` | `Delete` · `Quarantine` · `NeedsPairing` · `Retry` | |
| **NeuroPhobiaJson** | — (sealed) | `- sb : StringBuilder` | `+ BeginObject()` · `+ EndObject()` · `+ BeginArray()` · `+ EndArray()` · `+ Key(name)` · `+ Value(...)` · `+ Prop(name, value)` · `+ Iso(utc : DateTime) : string {static}` · `+ ToString() : string` (las de construcción devuelven `NeuroPhobiaJson`) |
| **DeviceContextDto** | `«DTO»` `[Serializable]` | `+ allowedStartLevel : int = 1` · `+ phobiaGrade : int` · `+ phobiaGradeUpdatedAt : string` · `+ recommendation : RecommendationDto` | `+ RecommendationText() : string` |
| **RecommendationDto** | `«DTO»` | `+ value : string` · `+ method : string` · `+ clinicalStatus : string` | |

## 3. Métricas (paquete `Metricas`)

| Clase | Estereotipo | Atributos | Operaciones |
|---|---|---|---|
| **MetricsCollector** : MonoBehaviour | — | `+ level : int` · `+ player : Transform` · `+ spider : Transform` · `+ spiderLayerName : string` · `+ avoidanceRetreatSpeed : float` · `- gazeTimeOnSpider : float` · `- avoidanceAttempts : int` · `- proximityMin : float` · `- breathingActivations : int` · `- levelAttempts : int` · `- handWithdrawals : int` · `- handContactDuration : float` · `+ SampleIntervalSeconds : float = 0.5 {const}` | `+ RegisterTaskCompletion(taskId : string)` · `+ SetSpiders(spiders : AranaController[])` · `+ RegisterBreathingActivation()` · `+ RegisterLevelAttempt()` · `+ RegisterHandWithdrawal()` · `+ AddHandContactTime(seconds : float)` · `+ BuildMetrics(passed : bool) : LevelMetrics` |
| **SessionReport** | `[Serializable]` | `+ sessionId : string` · `+ phobiaGrade : int` · `+ totalDuration : float` · `+ levelMetrics : List<LevelMetrics>` · `+ timestamp : string` · `+ testSession : bool` | |
| **LevelMetrics** | `[Serializable]` | `+ level : int` · `+ gazeTimeOnSpider : float` · `+ avoidanceAttempts : int` · `+ headMovementFrequency : float` · `+ proximityMin : float` · `+ taskCompletions : List<string>` · `+ breathingActivations : int` · `+ levelPassed : bool` · `+ sessionDuration : float` · `+ levelAttempts : int` · `+ handWithdrawals : int` · `+ handContactDuration : float` · `+ outcome : string` · `+ gazeMeanAngleDeg : float` · `+ sampleHz : float` · `+ distanceSamples : List<float>` · `+ angleSamples : List<float>` · `+ events : List<LevelEvent>` · `+ suds : List<SudsEntry>` | |
| **LevelEvent** | `[Serializable]` | `+ t : float` · `+ type : string` · `+ value : float` | |
| **SudsEntry** | `[Serializable]` | `+ phase : string` · `+ value : int` · `+ at : float` | |
| **TaskManager** : MonoBehaviour | — | `- completedTasks : HashSet<string>` | `+ IsCompleted(id : string) : bool` · `+ CompleteTask(taskId : string)` · `+ RefreshHUD()` |

## 4. Estímulo (paquete `Entidades`)

| Clase | Estereotipo | Miembros |
|---|---|---|
| **IPhobiaStimulus** | `«interface»` | `+ Pause()` · `+ Resume()` · `+ GetDistanceToPlayer() : float` · `+ SetMovementPattern(p : MovementPattern)` |
| **AranaController** : MonoBehaviour | — | `+ defaultPattern : MovementPattern` · `+ player : Transform` · `+ handTarget : Transform` · `+ moveSpeed : float = 0.35` · `+ patrolRadius : float = 1.5` · `- currentPattern : MovementPattern` · `- paused : bool` · `- startPosition : Vector3` · las cuatro operaciones de la interfaz |
| **MovementPattern** | `«enumeration»` | `IDLE` · `SLOW_PATROL` · `HAND_CRAWL` · `FREE_ROAM` |

## 5. Niveles (los controladores que usa cada escena)

Revisado contra las escenas `Assets/Scenes/Nivel1…5.unity`, es decir, los scripts que están puestos en cada escena.

| Escena | Clase | Paquete | Miembros principales / qué hace |
|---|---|---|---|
| Nivel1 | **Level1SequentialGazeFlow** : MonoBehaviour (sealed) | `NeuroPhobia_Level1Flow` | `- playerCamera : Camera` · `- cards : List<GameObject>` · `- nextSceneName : string = "Nivel2"` · al terminar llama a `GlobalSessionUI.CompleteLevel(1)` |
| Nivel1 | **Level1ExposureController** : MonoBehaviour | `NeuroPhobia_Levels123` | `+ GoToLevel2()` → `GlobalSessionUI.CompleteLevel(1)` |
| Nivel2 | **NeuroPhobiaLevel2StableGaze** : MonoBehaviour (sealed) | `NeuroPhobia_Level23Polish` | `+ metricsCollector : MetricsCollector` · registra métricas con `SessionManager.AddLevelMetrics` |
| Nivel3 | **Level3ProgressControllerV2** : MonoBehaviour | `NeuroPhobia_Levels123` | `+ metricsCollector : MetricsCollector` · `+ RegisterCheckpoint(order : int)` · `SessionManager.AddLevelMetrics` |
| Nivel3 | **Level3OrbSequenceFlow** : MonoBehaviour (sealed) | `NeuroPhobia_Level23Polish` | `- orbs : List<GameObject>` · `- spiderPatrol : Level3SpiderPatrolV2` · `- nextSceneName : string = "Nivel4"` |
| Nivel4 | **NPLevel4Controller** : MonoBehaviour (sealed, namespace `NeuroPhobia.Level45`) | `NeuroPhobia_Level45` | `+ spiderPatrol : NPNaturalSpiderPatrol` · `GlobalSessionUI.CompleteLevel(4)` |
| Nivel4 | **Level4ContactTimer** : MonoBehaviour | `Nivel4` | `+ metricsCollector : MetricsCollector` · `- contactSeconds : float` · `- completed : bool` · `SessionManager.AddLevelMetrics` |
| Nivel5 | **NPLevel5Controller** : MonoBehaviour (sealed, namespace `NeuroPhobia.Level45`) | `NeuroPhobia_Level45` | `+ spiderPatrols : NPNaturalSpiderPatrol[]` · `+ LoadMenu()` · `+ RestartLevel()` |
| Nivel5 | **Level5DomesticTaskManager** : MonoBehaviour | `Nivel5` | `+ metricsCollector : MetricsCollector` · `+ RegisterTask(taskId : string)` · `SessionManager.AddLevelMetrics` |
| Nivel5 | **Level5SpawnManager** : MonoBehaviour | `Nivel5` | `- spiders : AranaController[5]` |
| Nivel4, Nivel5 | **NPNaturalSpiderPatrol** : MonoBehaviour | `NeuroPhobia_Level45` | movimiento de las arañas de los niveles 4 y 5 |
| Nivel3 | **Level3SpiderPatrolV2** : MonoBehaviour | `NeuroPhobia_Levels123` | movimiento de la araña del nivel 3 |

## 6. UI y menú (resumen)

| Clase | Operaciones |
|---|---|
| **GlobalSessionUI** : MonoBehaviour (sealed) | `+ CompleteLevel(level : int) {static}` · `+ OfferRepeat(level : int, message : string) : bool {static}` · `+ ShowSessionSummary() {static}` |
| **NeuroPhobiaMainMenuModern** : MonoBehaviour | Menú principal: consentimiento, grado de fobia, emparejamiento. |
| **NeuroPhobiaMenuBridge** : MonoBehaviour | `+ LoadNivel1()` · `+ QuitApplication()` |
| **BreathingGuide** : MonoBehaviour | `- cycleSeconds : float = 19` · `- minScale : float` · `- maxScale : float` |

---

## Relaciones

| De | A | Tipo | Multiplicidad / nota |
|---|---|---|---|
| AranaController | IPhobiaStimulus | **Realization** | |
| AranaController | MovementPattern | Association (atributo) | |
| SessionManager | SessionReport | Composition | 1 — 1 |
| SessionReport | LevelMetrics | Composition | 1 — 0..* |
| LevelMetrics | LevelEvent | Composition | 1 — 0..* |
| LevelMetrics | SudsEntry | Composition | 1 — 0..* |
| SessionManager | FastAPIClient | Association (mismo GameObject, `GetComponent`) | 1 — 1 |
| FastAPIClient | RecordOutbox | Composition | 1 — 1 |
| FastAPIClient | DeviceContextDto | Association (caché) | 1 — 0..1 |
| DeviceContextDto | RecommendationDto | Composition | 1 — 1 |
| RecordOutbox | OutboxAction | Dependency `«use»` | |
| FastAPIClient | DeviceRecordMapper | Dependency `«use»` | |
| DeviceRecordMapper | NeuroPhobiaJson | Dependency `«create»` | |
| DeviceRecordMapper | LevelMetrics, SessionReport | Dependency `«use»` | |
| MetricsCollector | LevelMetrics | Dependency `«create»` (`BuildMetrics`) | |
| MetricsCollector | AranaController | Association | 1 — 0..* |
| GameStateManager | GameState | Association (atributo) | |
| GameStateManager | AranaController | Dependency (pausa y reanuda las arañas) | |
| LevelManager | LevelMetrics | Dependency `«use»` | |
| Level5SpawnManager | AranaController | Aggregation | 1 — 5 |
| NeuroPhobiaLevel2StableGaze, Level3ProgressControllerV2, Level4ContactTimer, Level5DomesticTaskManager, Level5SpawnManager, LevelBootstrap, LevelManager, TaskManager, MetricsCollector, GlobalSessionUI | SessionManager | Dependency `«use»` (`SessionManager.Instance`) | |
| NeuroPhobiaLevel2StableGaze, Level3ProgressControllerV2, Level4ContactTimer, Level5DomesticTaskManager, Level5SpawnManager, LevelCompletionTrigger, TaskManager, GlobalSessionUI | MetricsCollector | Association (campo `metricsCollector`) / Dependency | 1 — 1 |
| Level1SequentialGazeFlow, Level1ExposureController, NPLevel4Controller, Level4ContactTimer | GlobalSessionUI | Dependency `«use»` (`CompleteLevel`) | |
| NPLevel4Controller | NPNaturalSpiderPatrol | Association | 1 — 1 |
| NPLevel5Controller | NPNaturalSpiderPatrol | Aggregation | 1 — 1..* |
| Level3OrbSequenceFlow | Level3SpiderPatrolV2 | Association | 1 — 1 |
| NeuroPhobiaMainMenuModern, GlobalSessionUI | SessionManager, FastAPIClient | Dependency `«use»` (inicia la sesión, empareja, envía el grado de fobia, muestra el estado de envío) | |
| Todas las `: MonoBehaviour` | MonoBehaviour | **Generalization** | |

---

## 7. Clases sin uso aparente (no se dibujan)

No están en ninguna escena ni en ningún prefab propio, y ningún otro script las crea ni las referencia. Parecen restos de versiones anteriores:

- `Nivel2/`: `Level2GazeTimer`, `Level2HUD`, `Level2ExclusionZone`.
- `Nivel3/`: `Level3ProgressController`, `Level3Checkpoint`, `Level3AvoidanceMonitor`, `Level3SpiderMovement`. Las sustituyen las versiones `V2` de `NeuroPhobia_Levels123`.
- `Control/`: `Level1SpawnAlign`, `Level2SitToggle`, `Level2SpawnAlign`, `Level3OrbSpiders`, `Level3XRHud`, `SitTrigger`.
- `UI/`: `CanvasManager`, `IndicadorAnsiedad`, `BarraEstres`, `ExclusionZoneMessage`.
- `NeuroPhobia_*`: `Level2ScreenGazeFlow`, `NeuroPhobiaLevel2SafeDistance`, `Level2SafeDistanceController`, `Level3CheckpointV2`, `NeuroPhobiaLevel3OrbCompatibility`.

`AdaptiveCommandPoller` sí está en las escenas, pero está vacío y desactivado. `XRBootstrap` y `GlobalSessionUI` no están en las escenas porque se crean por código (`RuntimeInitializeOnLoadMethod` / `AddComponent`).

Si se dibujan, conviene marcarlas `«deprecated»`.
