# Extensiones para la demostración académica

Estado: implementación local; pendiente de aceptación y despliegue. Complementa el contrato v1.1.0, sin cambiar los sobres de registros, la autenticación ni los valores de recomendación. El OpenAPI adjunto describe la implementación actual.

## Resultado al finalizar

El servidor analiza sesiones con inicio y cierre recibidos y `testSession=false`. Conserva `rules-baseline`: la IA externa no decide niveles ni cambia `allowedStartLevel`. Los registros tardíos recalculan las reglas; si cambian los datos utilizados, invalidan el resumen anterior.

`AnalysisOut` incorpora `explanation`, `evaluatedLevel`, `evaluatedAttempt`, `narrative`, `narrativeStatus`, `narrativeModel` y `narrativeCreatedAt`. Los estados son `disabled`, `pending`, `generating`, `generated`, `fallback` y `quota_exceeded`. La explicación por reglas está disponible mientras se redacta el resumen o cuando este falla.

Los elementos de retroalimentación añaden `totalDurationSeconds` y `comparison`. La comparación usa la sesión anterior cerrada, no de prueba, que terminó antes del inicio actual. Devuelve diferencias de nivel alcanzado y duración. Solo compara el índice cuando coinciden método, versión y nivel realmente evaluado; las filas antiguas sin ese dato no son comparables. Estas diferencias no acreditan mejoría clínica.

`GET /device/context` añade `lastFeedback` con el mismo resultado persistido que consulta la web. Puede ser nulo. El visor consulta al volver al Refugio; no consulta Groq. No se devuelve identidad personal ni notas profesionales. El cliente debe comparar `sessionId` para no presentar un resultado anterior como si fuera el de la sesión recién cerrada.

## Descarga del APK

- `GET /public/app-release`: metadatos sin autenticación. `status`: `unavailable`, `pending_validation` o `available`. Sin URL S3 ni rutas internas.
- `GET /admin/app-release/download`: solo administración; APK binario, `private, no-store` y `X-Content-SHA256`. Sin sesión devuelve 401, otros roles 403, versión no apta 409, fallo de almacenamiento/integridad 503.
- Directorio opcional `NP_APK_RELEASE_DIRECTORY`: contiene `release.json` y su APK. Ausente significa que no hay instalador publicado.
- El manifiesto exige nombre simple, tamaño, SHA-256, versión, revisión Git completa y URL HTTPS. Solo se habilita con `signedForDistribution=true`, `debuggable=false`, `sourceDirty=false`, `headsetTested=true` y `distributionReady=true`. Estos indicadores requieren revisión del artefacto real: no son una certificación automática.

## Persistencia

La migración `0004` añade columnas opcionales a `clinical.analyses` y la tabla `clinical.narrative_usage`. No borra datos. En EC2 se ejecuta como propietario y se conceden permisos a `np_app`. No se ha ejecutado en AWS desde este PC.
