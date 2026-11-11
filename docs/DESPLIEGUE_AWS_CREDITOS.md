# Migración a AWS con créditos: NEUROPHOBIA

> Propuesta histórica descartada por decisión del usuario. La arquitectura elegida y autorizada es [EC2 con PostgreSQL juntos](DESPLIEGUE_AWS_EC2.md), sin Lambda ni RDS. Los scripts Lambda de esta propuesta se retiraron.

Estado: implementación preparada y validada localmente; **no desplegada**. La creación de recursos quedó pendiente de aprobación explícita de la arquitectura. No hay URL AWS operativa todavía.

## Alcance y situación encontrada

El frontend es una SPA React/Vite. Usa `/api/v1`, JWT de acceso en memoria y cookie de refresco HttpOnly, Secure, SameSite=Strict. Su proxy de Vercel mantiene el mismo origen entre web y API. Publicar solo los archivos en S3 sin enrutar la API rompería ese comportamiento.

El backend es FastAPI, SQLAlchemy, psycopg y Alembic. Los esquemas `identity` y `clinical` contienen identidades y registros clínicos separados; dependen de relaciones, transacciones, JSONB y bloqueos PostgreSQL. La autenticación pertenece a FastAPI: el código revisado no usa Supabase Auth ni su SDK de almacenamiento. No hace falta sustituir la autenticación por Cognito para mover este sistema.

La rama local original del backend estaba en v1 y contenía cambios sin confirmar. La web usaba v1.1. La copia `NP_AWS_Back` parte de la referencia local `origin/feat/aws-deployment` (080946d), que incluye el contrato v1.1 y los contadores compartidos de intentos en PostgreSQL. La copia `NP_AWS_Front` conserva el frontend existente. Los directorios originales se preservaron; no se fusionaron ramas ni se hizo push.

No se proporcionaron conexión ni exportación de Supabase. No se ha inspeccionado su contenido ni comprobado si hay datos. El despliegue preparado crea una base nueva. **No equivale a haber migrado datos existentes ni a haber sustituido un servicio en producción.**

## Arquitectura elegida

```text
Navegador / Meta Quest
       HTTPS
         |
     CloudFront (dominio AWS, mismo origen)
         |-- web: S3 privado, Origin Access Control
         |-- /api/*: HTTPS -> API Gateway HTTP API
                                    |
                              Lambda / FastAPI
                                    | TLS verify-full
                            RDS PostgreSQL 17.9
                            subredes privadas en Ohio

APK -> otro bucket S3 privado, versiones + SHA-256
Migraciones -> otra Lambda, invocación administrativa con IAM
Credenciales -> Secrets Manager, referencias dinámicas de CloudFormation
Logs y alarmas -> CloudWatch
```

Los recursos regionales se crean en `us-east-2`. CloudFront es global; el kit usa su endpoint de `us-east-1`. No se usa Lambda@Edge ni replicación entre regiones.

RDS `db.t4g.micro`, Single-AZ, 20 GiB gp3 cifrados, sin acceso público. Solo admite conexiones desde el grupo de seguridad de Lambda, en el puerto 5432. No se crean NAT, endpoints privados facturables, EC2, balanceador, ECS ni RDS Proxy. Lambda recibe los secretos al desplegar, por lo que no necesita acceder a Secrets Manager desde la VPC en cada arranque.

La Lambda pública usa `np_app`, con permisos de lectura/escritura sobre las tablas y secuencias de aplicación. La función administrativa aplica Alembic con `np_owner`, crea el usuario de ejecución y concede sus permisos. Las migraciones no se ejecutan en cada petición ni en cada arranque en frío. Ninguna ruta HTTP permite invocar la función administrativa.

CloudFront sobrescribe la IP del visitante y añade un secreto al origen; el adaptador Lambda rechaza peticiones sin ese secreto. Se conservan permisos por rol y validación JWT del backend. La API y las cookies no se cachean. Las rutas de navegación React se reescriben a `index.html` sin convertir errores de la API en páginas HTML. API Gateway limita el tráfico a 5 solicitudes/s y ráfagas de 10; no es un límite monetario absoluto.

## Disponibilidad durante meses y costo

Consulta real del proyecto realizada el 9 de noviembre de 2026:

| Concepto | Valor |
|---|---|
| Perfil | `neurophobia` |
| Plan | FREE, ACTIVE |
| Crédito restante | 100 USD |
| Vencimiento comunicado por AWS | 9 de mayo de 2027, 17:55 hora de Bogotá |

Precios de lista consultados con AWS Pricing para Ohio; cálculo con 730 horas/mes:

| Recurso | Base mensual USD |
|---|---:|
| RDS db.t4g.micro: 0,016 USD/h | 11,68 |
| RDS gp3: 20 GiB a 0,115 USD/GiB-mes | 2,30 |
| Un secreto de Secrets Manager | 0,40 |
| **Base mensual estimada** | **14,38** |
| **Seis meses de esa base** | **86,28** |

Quedarían aproximadamente 13,72 USD de los 100 para seis meses de tráfico, solicitudes, APK, versiones de objetos, Lambda, API Gateway, logs y alarmas, sujeto a beneficios aplicables. También pueden existir cargos por CPU extra de instancias burstable si la carga sostenida supera su base. El costo variable y la disponibilidad **no están garantizados** por esta estimación. La distribución del APK puede aumentar mucho la transferencia; permanece privada por defecto.

Se conservan el plan FREE y sus límites; el procedimiento no cambia al plan de pago ni compra reservas. Los créditos tienen duración limitada y pueden acabarse antes por consumo. Para seguir después del vencimiento se necesitará otra decisión de financiación y plan: no hay una base PostgreSQL administrada gratuita e indefinida en este diseño. Revisar saldo y gasto en AWS Settings > Billing.

RDS permanece encendido, sin detenerse por inactividad. Lambda atiende solicitudes bajo demanda y puede tener arranques en frío; no necesita un proceso local ni el PC encendido. Single-AZ es una limitación deliberada de costo: no ofrece conmutación automática entre zonas. Para alta disponibilidad de producción habría que aumentar el presupuesto.

## Preparación y despliegue

Archivos de implementación: `infra/aws-lite/deploy.py`, `infra/aws-lite/package.py`, `aws_lambda.py`, `requirements-aws.txt` y certificado público `rds-ca.pem`.

Desde la carpeta que contiene ambas copias:

```powershell
# Utilizar un entorno Python 3.12 de despliegue con boto3[crt].
uv pip install --python NP_Back/.venv/Scripts/python.exe 'boto3[crt]'

# Certificado público de confianza para TLS de RDS.
Invoke-WebRequest https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem -OutFile NP_AWS_Back/rds-ca.pem
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/package.py

$env:VITE_USE_MOCKS = 'false'
$env:VITE_API_BASE_URL = '/api/v1'
npm --prefix NP_AWS_Front ci
npm --prefix NP_AWS_Front run build

# Ejecutar solo tras aprobar los recursos y el consumo de créditos.
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/deploy.py deploy
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/deploy.py status
```

El comando deploy comprueba el plan FREE activo y al menos 90 USD de saldo antes de crear recursos. Es una protección inicial, no un presupuesto ni un sistema que limite automáticamente el gasto. Usa secretos aleatorios en memoria y Secrets Manager; no escribe sus valores en archivos ni imprime credenciales.

Esperar `CREATE_COMPLETE` o `UPDATE_COMPLETE`. Si falla, revisar eventos de CloudFormation; no publicar la web sobre una pila incompleta. Los buckets y secretos iniciales pueden persistir si falla CloudFormation y deben inventariarse antes de reintentar.

```powershell
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/deploy.py migrate
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/deploy.py publish
```

La salida `WebUrl` será el dominio HTTPS público. Probar `/api/v1/health` y `/api/v1/health/ready`, registro de prueba, login, recarga con refresco, logout, roles, notas y vinculación del visor. La validación local no reemplaza estas pruebas del despliegue real. Si ese origen tuvo MSW, retirar el worker de demostración antes de probar.

## Datos de Supabase y cambio de servicio

Antes del cambio definitivo, verificar si hay datos y la versión de Alembic en el origen. Si existen, pausar escrituras y obtener un dump cifrado de los esquemas de la aplicación con `pg_dump`, sin copiar los esquemas internos de Supabase. Restaurar en una base vacía con el propietario de migraciones, revisar propietarios y privilegios, y después aplicar Alembic pendiente. No mezclar una restauración de estructura completa con tablas ya creadas por Alembic.

Comparar conteos, claves foráneas, UUID, consentimientos, hashes de contraseñas, sesiones y registros; comprobar también los ejemplos del contrato. Si deben conservarse sesiones y emparejamientos, migrar los secretos de firma/HMAC mediante un canal seguro, en vez de generar claves incompatibles. De lo contrario, planificar cierre de sesiones y nuevo emparejamiento. No incluir dumps, claves ni datos personales en Git ni en mensajes.

Conservar temporalmente Vercel/Supabase hasta verificar AWS. Tras aceptar escrituras en AWS, volver al origen antiguo sin sincronizar datos produciría pérdida de cambios: el rollback requiere restauración/sincronización, no solo cambiar una URL. La eliminación del origen no forma parte del script.

## APK y visor

Se localizó `NeuroPhobia_Entrega_Final - copia/a}.apk`, de 240.890.221 bytes, modificado el 9 de noviembre de 2026. No se ha subido ni ejecutado.

Después del despliegue:

```powershell
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/aws-lite/deploy.py apk --apk-path 'NeuroPhobia_Entrega_Final - copia/a}.apk'
```

El script almacena el APK por su SHA-256, con tipo MIME Android y nombre de descarga `neurophobia.apk`. Guarda un manifiesto privado `releases/latest.json`; S3 conserva versiones. No se publica un enlace permanente. Para una descarga autorizada, generar una URL temporal con `aws s3 presign s3://BUCKET/CLAVE --expires-in 900 --profile neurophobia --region us-east-2`. La URL es una credencial temporal: compartirla solo con su destinatario y no registrarla públicamente.

El cliente Unity revisado permite configurar `backend_url.txt` dentro de `Application.persistentDataPath` y `SetBaseUrl`, además del campo del Inspector. Acepta el dominio AWS con o sin `/api/v1`. Esto podría permitir configurar el APK sin recompilar; falta comprobar que ese binario incluye esa versión y probarlo en Meta Quest. No se modificó ni abrió Unity.

## Copias, operación y recuperación

RDS tiene copias automáticas y recuperación a un punto en el tiempo durante siete días. Objetivo orientativo: RPO de minutos dentro de esa ventana y RTO de decenas de minutos, **sin garantía y pendiente de ensayo de restauración**. La restauración crea otra instancia y genera costo adicional temporal; probarla solo con el margen aprobado. Los snapshots finales se conservan, pueden generar costo y no sustituyen un backup verificado.

La pila tiene protección contra terminación y la base contra borrado. Los buckets se retienen. No hay borrado automático por inactividad. Antes de actualizar, revisar los cambios de CloudFormation, comprobar backup reciente y evitar reemplazos de RDS. Guardar el artefacto anterior para rollback de código; la reversión del esquema requiere un procedimiento propio.

CloudWatch conserva logs Lambda siete días y alarmas para errores API y poco espacio de RDS. No hay correo configurado: se revisan en consola. No se activaron logs de acceso S3 ni eventos de datos CloudTrail por su costo adicional; se recomienda habilitarlos si se aprueba ese margen. Revisar costo y crédito periódicamente y el estado del proyecto antes de una demostración. El presupuesto documentado no es una alerta ni un corte automático.

## Validación realizada y pendiente

- Backend v1.1: 119 pruebas aprobadas con PostgreSQL efímero.
- Adaptador Lambda: 2 pruebas adicionales aprobadas, incluido rechazo del origen directo.
- Frontend: TypeScript y build de producción aprobados; 49 pruebas aprobadas con `NODE_OPTIONS=--no-experimental-webstorage` en Node 26.8.1; 4 pruebas del proxy heredado y verificación UTF-8 aprobadas.
- AWS `ValidateTemplate`: aprobada, requiere `CAPABILITY_IAM`.
- Paquete Linux Python 3.12 generado: aproximadamente 22 MB comprimido.
- Auditoría npm: avisos preexistentes en Vitest/tinypool/mocker, herramientas de desarrollo. No se publica un servidor de pruebas en AWS. La actualización mayor queda separada de la migración.
- Pendiente: aprobación de creación, despliegue real, migraciones RDS, comprobación del origen Supabase, primer administrador, pruebas HTTPS/cookies/roles, subida y prueba del APK y ensayo de restauración.
