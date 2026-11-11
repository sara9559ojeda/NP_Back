# Retroalimentación final con Groq

## Decisión

Groq es un redactor opcional de la demostración académica. El método existente `rules-baseline` conserva la autoridad sobre el índice técnico y la recomendación. El profesional conserva la decisión sobre el nivel inicial permitido. No se incorpora un chatbot, un diagnóstico ni un sistema de tratamiento autónomo.

Modelo inicial: `openai/gpt-oss-20b` servido por Groq. La API emplea JSON Schema estricto; se valida la recomendación contra la de reglas, el tamaño de la respuesta y contenido básico. Estas comprobaciones no garantizan la veracidad de un modelo: el texto se marca para revisión profesional y se conserva la explicación verificable por reglas.

## Recorrido

1. Unity envía inicio, intentos y cierre a la API existente.
2. El backend calcula las reglas y guarda el resultado. Las sesiones de prueba no se analizan.
3. Si la integración está habilitada, un trabajador dentro de la API reserva una solicitud del contador diario compartido en PostgreSQL.
4. Envía únicamente métricas técnicas resumidas: nivel, intento, duración, motivo de cierre, señales, índice, método y recomendación. No envía identificadores, nombres, correos, notas profesionales ni muestras crudas.
5. Guarda el texto validado una vez. Web y Refugio leen ese mismo registro. No se llama al proveedor en cada consulta.
6. Si llegan datos tardíos distintos, se invalida el texto anterior. Una respuesta que haya quedado obsoleta no sobrescribe el análisis nuevo.

## Configuración privada

Solo en el backend, mediante variables de entorno; nunca `VITE_`, APK ni repositorio:

```dotenv
NP_EXTERNAL_AI_ENABLED=true
NP_GROQ_API_KEY=<configurar fuera del chat>
NP_GROQ_MODEL=openai/gpt-oss-20b
NP_GROQ_DAILY_REQUEST_LIMIT=25
NP_GROQ_TIMEOUT_SECONDS=8
```

Sin habilitación explícita o sin clave, continúa la explicación por reglas. Límite 0 impide las solicitudes. Para detener llamadas nuevas, deshabilitar la integración y reiniciar el contenedor. Los resúmenes ya guardados permanecen consultables; habilitarla no reenvía automáticamente todo el historial.

En el servidor EC2 existente, `config/groq.env` debe pertenecer a root con permisos 600. `infra/ec2/update_runtime.py` lo incorpora si existe. No imprimir `docker inspect` completo, archivos de entorno ni respuestas con secretos en un informe. Configurar la clave en la máquina autorizada y no pegarla en un chat.

## Límites y fallos

- 25 solicitudes diarias por defecto, compartidas entre procesos y persistentes tras reinicio. Día UTC.
- Hasta 512 tokens de salida por solicitud. Una llamada por versión del análisis; sin reintentos HTTP automáticos. Una interrupción del proceso puede recuperar el trabajo después de dos minutos y consumir otra reserva.
- Respuesta limitada a 64 KiB; timeout de red 8 segundos por operación; sin redirecciones.
- 429, timeout, respuesta inválida y cuota local agotada conservan la explicación por reglas. No hay cambio automático a un proveedor de pago.
- Mantener cuenta y clave del plan gratuito de Groq. El límite local cuenta solicitudes, no dólares; no garantiza un precio si se cambia el plan. AWS y Groq tienen cuotas independientes. No se crea infraestructura AWS adicional.

## Datos y validación

Usar datos ficticios en esta demostración. Las métricas pueden seguir siendo datos de salud aunque se excluya la identidad; no habilitar envíos de sesiones reales sin revisar consentimiento, finalidad, acceso y política del proveedor. Groq describe excepciones de conservación por fiabilidad y abuso: no prometer retención cero.

Las pruebas locales usan un transporte HTTP simulado y PostgreSQL real temporal. Verifican cuota concurrente, petición única, respuesta 429, límites, respuesta obsoleta y coincidencia web/visor. Falta una llamada real con clave privada y revisión humana del texto obtenido.

Fuentes oficiales consultadas el 10-11-2026: [Structured outputs](https://console.groq.com/docs/structured-outputs), [API](https://console.groq.com/docs/api-reference), [límites](https://console.groq.com/docs/rate-limits) y [datos](https://console.groq.com/docs/your-data). Confirmar el modelo y los límites de la cuenta al activarla.
