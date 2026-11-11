# NEUROPHOBIA: EC2 y PostgreSQL juntos

Arquitectura autorizada por Sara el 9 de noviembre de 2026, para aproximadamente cuatro meses de uso académico. Región: `us-east-2`. Perfil local: `neurophobia`. Pila: `neurophobia-ec2`, estado `UPDATE_COMPLETE` tras el cierre del grupo de seguridad.

Web y raíz del cliente VR: **https://d2jh1px5hj3b01.cloudfront.net**. API: **https://d2jh1px5hj3b01.cloudfront.net/api/v1**.

Instancia: `i-062da0e63e90f0ac5`. Distribución: `E1CHP3Y3I5XA4O`. Bucket privado: `neurophobia-ec2-402597555057-us-east-2`. Los identificadores no son credenciales.

## Arquitectura y disponibilidad

```text
Navegador / Meta Quest
        HTTPS
           |
      CloudFront
           | conexión privada de origen VPC
      EC2 t3.small, Amazon Linux 2023
           |-- nginx: archivos de la SPA y proxy /api/*
           |-- FastAPI: contenedor no root, 127.0.0.1:8000
           |-- PostgreSQL 17.9: contenedor sin puerto publicado
           |-- EBS gp3 20 GiB cifrado: datos persistentes

S3 privado: artefactos, APK versionado y backups diarios
SSM: administración sin SSH, secretos SecureString
CloudWatch: recuperación del host, disco y éxito de backups
```

La instancia permanece encendida: no hay apagado por inactividad, Lambda, RDS, NAT, balanceador ni tareas programadas de suspensión. Docker y nginx arrancan con el sistema; los contenedores reinician si fallan. Un temporizador comprueba la API cada cinco minutos y la reinicia si falla dos veces consecutivas. Una alarma intenta recuperar la instancia ante un fallo de hardware compatible con EC2 recovery.

No es una arquitectura de alta disponibilidad: un fallo de máquina, mantenimiento o recuperación puede causar interrupciones. CloudFront cifra el acceso del usuario mediante HTTPS; el tramo CloudFront–EC2 usa HTTP dentro del origen VPC privado. La base solo se comunica por la red Docker interna, sin exposición de 5432. La dirección pública de EC2 se usa para salida a SSM, descargas y backups. El grupo de seguridad se restringe al grupo de servicio CloudFront antes de entregar la web; no hay entrada SSH.

## Compatibilidad y seguridad de aplicación

Se conserva el frontend React/Vite con `VITE_USE_MOCKS=false`, API relativa `/api/v1`, tokens de acceso en memoria y cookie de refresco HttpOnly, Secure y SameSite=Strict. CloudFront y nginx entregan web y API en el mismo dominio. Las respuestas autenticadas no se cachean; las rutas React usan el fallback `index.html` sin convertir errores de API en páginas HTML.

La copia `NP_AWS_Back` parte de la referencia local `origin/feat/aws-deployment` (080946d), que contiene el contrato v1.1 utilizado por la web y límites de intentos compartidos en PostgreSQL. El checkout original de NP_Back conservó sus cambios locales. Los repositorios originales de frontend, backend y Unity no se reemplazaron ni se fusionaron con estas copias.

El propietario `np_owner` aplica Alembic al desplegar. FastAPI usa `np_app`, con permisos de lectura/escritura en `identity` y `clinical`, sin permisos para modificar su estructura. Los secretos se generan aleatoriamente y se guardan como SSM SecureString; se leen usando el perfil de instancia y se escriben únicamente en archivos root de modo 0600 dentro de `/opt/neurophobia/config`. No hay claves AWS estáticas en el servidor. IMDSv2 es obligatorio y el hop limit impide que los contenedores obtengan credenciales del host.

CloudFront sobrescribe la IP del visitante. nginx añade el secreto compartido de proxy al backend, que aplica los límites de intentos sin confiar en cabeceras arbitrarias de internet. La autenticación y los permisos por rol siguen siendo responsabilidad de FastAPI.

## Costos y cuatro meses

El proyecto se verificó con plan FREE activo, saldo de 100 USD y vencimiento del plan comunicado por AWS el 9 de mayo de 2027. No se cambia al plan de pago.

| Base de lista aproximada, 730 horas/mes | USD/mes |
|---|---:|
| EC2 t3.small Linux: 0,0208 USD/h | 15,18 |
| 20 GiB EBS gp3 | 1,60 |
| Una IPv4 pública | 3,65 |
| **Base** | **20,43** |
| **Base por cuatro meses** | **81,74** |

Se añaden S3, descargas del APK, solicitudes CloudFront, backups, métricas/alarmas e impuestos que correspondan. Dos métricas personalizadas y tres alarmas pueden añadir hasta aproximadamente 0,90 USD/mes a precio de lista si no están cubiertas por beneficios. El saldo de créditos no equivale a un límite técnico de gasto y su actualización puede tener retraso. Revisar consumo y saldo en AWS Settings > Billing.

EC2 usa créditos de CPU en modo `standard`: no genera cargos por CPU excedente, pero puede perder rendimiento bajo carga sostenida. El margen se dimensionó para un prototipo de bajo tráfico, no para garantizar un volumen ilimitado de usuarios o descargas. Mantener la instancia después del plazo sigue consumiendo créditos hasta que se tome otra decisión; no se programó su apagado.

## Desplegar y administrar

Los scripts están en `infra/ec2`. No ejecutar los antiguos scripts Fargate ni la propuesta histórica Lambda.

```powershell
# Desde la carpeta que contiene NP_AWS_Back y NP_AWS_Front.
$env:VITE_USE_MOCKS='false'
$env:VITE_API_BASE_URL='/api/v1'
npm --prefix NP_AWS_Front run build
docker build --platform linux/amd64 -t neurophobia-api:ec2-20261109 NP_AWS_Back
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/deploy.py prepare
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/deploy.py plan
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/validate.py
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/deploy.py deploy
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/deploy.py status
```

`deploy` se niega a crear otra pila sobre la existente y exige FREE activo con al menos 90 USD de saldo para el primer despliegue. Las actualizaciones requieren revisar un change set para no reemplazar accidentalmente la instancia y sus datos. Los artefactos se identifican por SHA-256. No lanzar de nuevo una instancia como forma de actualizar el código.

Tras terminar CloudFormation, ejecutar `harden` y esperar que termine la actualización. Sustituye la regla inicial de la lista administrada CloudFront por el grupo de seguridad del servicio de origen VPC. Verificar que la instancia no admite 22 ni 5432 desde internet.

`outputs.json` contiene identificadores y el dominio público, no contraseñas. Para administrar, usar Session Manager o `deploy.py command` / `command-result`. La cuenta inicial de administrador debe crearse con nombre y correo elegidos por la propietaria, sin enviar contraseñas por el chat. La CLI de aplicación original permite su creación interactiva.

## Backups, restauración y datos existentes

Una copia lógica PostgreSQL en formato custom se envía diariamente a `backups/` del bucket S3 privado, mediante HTTPS y cifrado SSE-S3. Se conserva catorce días. La carpeta de datos Docker está en EBS cifrado y permanece tras reinicios. La instancia tiene protección contra terminación; CloudFormation y el volumen conservan datos si se solicita un borrado. Estas protecciones no sustituyen los backups.

RPO objetivo: hasta 24 horas. RTO depende del aprovisionamiento y restauración; no se promete cero pérdida ni recuperación instantánea. Antes de cualquier cambio mayor, ejecutar `/opt/neurophobia/infra/backup.sh`. Para comprobar una copia, restaurarla en una base temporal y comparar tablas y conteos; no restaurar sobre producción sin detener escrituras y preparar rollback.

El usuario de sistema `np_owner` es necesario para crear el rol y aplicar estructura; para restaurar en otra instalación, crear los roles y secretos de forma segura y después restaurar sin copiar esquemas internos de otro proveedor. Preservar las claves de firma/HMAC si se quieren conservar sesiones y emparejamientos. `infra/ec2/restore_check.sh` restaura la copia más reciente en una base temporal, compara tablas y conteos, y la elimina al terminar.

No se recibieron acceso ni exportación de Supabase. La base AWS se inicializa vacía; esto no certifica una transferencia de datos desde Supabase. No eliminar Vercel ni Supabase hasta verificar si hay información y completar el cambio de clientes. Una reversión después de recibir datos en AWS necesita sincronización, no solo cambiar una URL.

## APK

El APK se almacena privadamente en `releases/<sha256>/neurophobia.apk`, con tipo MIME Android, versión S3 y manifiesto `releases/latest.json`. No se distribuye públicamente por defecto.

```powershell
NP_Back/.venv/Scripts/python.exe NP_AWS_Back/infra/ec2/deploy.py apk --apk-path 'NeuroPhobia_Entrega_Final - copia/a}.apk'
```

Crear un enlace temporal solo para los destinatarios autorizados con `aws s3 presign`, perfil `neurophobia`, región `us-east-2`, y no publicar esa URL como enlace permanente.

El código Unity revisado lee `backend_url.txt` desde `Application.persistentDataPath` y admite configurar la URL por `SetBaseUrl`. Usar la salida `WebUrl`, con o sin `/api/v1`. Es necesario verificar que el APK encontrado incluye esa versión y probar envío y emparejamiento en Meta Quest. No se abrió Unity ni se recompiló el APK.

## Validación

Antes del despliegue: 119 pruebas del backend, 49 del frontend, build/TypeScript, cuatro pruebas del proxy heredado y UTF-8 aprobados. En Node 26 se usó `NODE_OPTIONS=--no-experimental-webstorage` para resolver el conflicto con jsdom. Los avisos npm preexistentes se concentran en herramientas de pruebas que no se publican como servicios.

Infraestructura: cfn-lint sin hallazgos; guard comprobó IMDSv2, cifrado EBS inline, retención, protección de terminación, perfil IAM y ausencia de Lambda/RDS/NAT/ALB. La regla oficial de volúmenes independientes marca SKIP porque el disco se declara dentro de la instancia; la regla específica de disco inline sí se evalúa. AWS ValidateTemplate aprobado. El ejecutable local cfn-lint fue bloqueado por Control de aplicaciones; se utilizó la API Python documentada del mismo validador instalado.

Verificación efectiva del despliegue:

- cloud-init terminó y las migraciones llegaron a `0003`.
- nginx, Docker y los temporizadores de backup y salud están habilitados y activos.
- EC2 usa `standard` para créditos CPU; EBS gp3 está cifrado.
- El único ingreso del grupo de seguridad es TCP 80 desde el grupo privado de servicio CloudFront; no hay rangos públicos ni puertos 22/5432.
- HTTPS y rutas SPA funcionan; `/api/v1/health/ready` devuelve base de datos `ok`.
- Administrador: login, cookie Secure/HttpOnly/SameSite=Strict, refresh, logout y rechazo del refresh tras logout comprobados.
- Permisos: administrador sin acceso clínico de profesional, paciente sin acceso administrativo.
- Registro técnico ficticio, emparejamiento de dispositivo, consulta de contexto y revocación al retirar consentimiento comprobados. Los pacientes de prueba retiraron su consentimiento; no son participantes reales.
- Respaldo real restaurado en una base temporal: mismas tablas y conteos de filas. Se eliminó la base temporal al terminar y se solicitó otra copia tras las pruebas.
- APK de 240.890.221 bytes guardado con cifrado AES256 y SHA-256 `9e994f604ce2f4f7114d9e7e7fc2defbf7ef8db419adab1c060fe8f237a03eed`.

Durante la puesta en marcha se corrigió la publicación del puerto Docker: PostgreSQL permanece en la red interna y la API usa además un bridge para publicar únicamente `127.0.0.1:8000` al host. La corrección está en `setup.py` y fue aplicada al servidor sin reemplazar la base ni la instancia. La imagen de la aplicación no necesitó cambios. El paquete local se regeneró con esta corrección para futuras instalaciones.

Administrador inicial: creado con el correo de la propietaria. Su contraseña se guarda solo en un archivo local protegido, fuera de los repositorios. El parámetro SSM temporal usado para crearlo fue eliminado. Cambiar la contraseña desde la aplicación después del primer acceso.

Pendientes fuera de las pruebas realizadas: ensayo físico del APK en Meta Quest con la URL AWS, verificación/importación de información de Supabase si existe, revisión clínica de textos y operación/costos durante los cuatro meses. No se apagaron ni eliminaron Vercel/Supabase ni se programó apagado automático de EC2.
