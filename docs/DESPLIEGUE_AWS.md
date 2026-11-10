# Desplegar NEUROPHOBIA en AWS (alternativa a Vercel + Supabase)

> Para el proyecto con plan FREE, 100 USD de créditos y región us-east-2, usa [EC2 con PostgreSQL juntos](DESPLIEGUE_AWS_EC2.md). El diseño Fargate/ALB descrito debajo no es el elegido para ese proyecto.

Esta guía despliega **todo el sistema** (NP_Back y NP_Front) en una cuenta de AWS con un solo comando, y lo borra con otro. La infraestructura está escrita como código con AWS CDK (TypeScript) en [`infra/aws`](../infra/aws). El despliegue en Vercel sigue funcionando igual; esto es una alternativa, no un reemplazo.

> Preparar no es desplegar: nada de este repositorio crea recursos en AWS hasta que tú ejecutes `deploy-aws`. Usa datos ficticios en la primera prueba.

## 1. Arquitectura

```text
Navegador / visor Unity
        │  HTTPS (un solo dominio: https://dxxxx.cloudfront.net)
        ▼
┌─────────────────── Amazon CloudFront ───────────────────┐
│  /*         → S3 privado (NP_Front compilado, OAC)      │
│  /api/v1/*  → origen VPC → ALB interno (sin caché)      │
│     · añade x-np-proxy-secret (Secrets Manager)         │
│     · función: x-np-client-ip = IP real del visitante   │
└──────────────────────────────┬──────────────────────────┘
                               │ red privada de AWS
┌────────────────────── VPC (2 zonas) ────────────────────┐
│  subred aislada: ALB interno ──► ECS Fargate (NP_Back)  │
│                                   · alembic upgrade head│
│                                   · logs → CloudWatch   │
│  subred aislada: RDS PostgreSQL 17 (cifrado, TLS)       │
└─────────────────────────────────────────────────────────┘
Secrets Manager: NP_SECRET_KEY, NP_PROXY_SECRET, credenciales de RDS
```

Se crean dos pilas de CloudFormation:

| Pila | Contenido | Por qué separada |
| --- | --- | --- |
| `NeurophobiaData` | VPC, grupos de seguridad, RDS PostgreSQL y su secreto | Contiene datos clínicos. Tiene protección contra borrado y RDS deja una instantánea final. |
| `NeurophobiaApp` | ECS Fargate, ALB interno, CloudFront, S3, secretos de la app, alarmas | No tiene estado. Se puede borrar y volver a crear sin perder datos. |

### Justificación de las decisiones

- **Backend en ECS Fargate.** Reutiliza el `Dockerfile` y el `docker/entrypoint.sh` que ya existen. El entrypoint ejecuta `alembic upgrade head` antes de arrancar uvicorn, así que **cada despliegue aplica las migraciones automáticamente** antes de que la tarea nueva reciba tráfico. Si la tarea no queda sana, el *circuit breaker* de ECS vuelve a la versión anterior.
  - App Runner se descartó porque dejó de aceptar clientes nuevos el 30 de abril de 2026.
  - Lambda se descartó porque, para llegar a RDS dentro de la VPC, habría necesitado un NAT o endpoints de VPC (con un coste parecido). Además, las migraciones no tienen un sitio natural en un arranque en frío.
- **Base de datos en RDS PostgreSQL 17** (db.t4g.micro, una zona, 20 GiB gp3 cifrados, copias de seguridad de 7 días). Va en subredes aisladas, sin IP pública y con TLS obligatorio. Con `database.mode = "external"` puedes seguir usando Supabase (sección 6).
- **Un solo dominio para la web y la API.** CloudFront sirve NP_Front y envía `/api/v1/*` al backend. La cookie de refresco (HttpOnly, Secure, SameSite=Strict, ruta `/api/v1/auth`) sigue siendo *first-party*, exactamente como con el proxy `api/proxy.mjs` de Vercel. No hace falta cambiar nada en NP_Front.
- **Sin NAT Gateway.** Un NAT cuesta unos 33 USD al mes, más que todo lo demás junto.
  - Las tareas de Fargate están en subredes públicas con IP pública, para descargar la imagen y leer los secretos.
  - Su grupo de seguridad **solo acepta tráfico del ALB**.
  - El ALB es **interno**: no tiene IP pública y solo CloudFront llega a él, a través de un *VPC origin*.
- **Secretos.** Todos los secretos están en Secrets Manager y ECS los inyecta al arrancar el contenedor. Ningún secreto aparece en el código, en los parámetros ni en la salida de los scripts.
  - `NP_SECRET_KEY` y `NP_PROXY_SECRET` se generan al desplegar.
  - La contraseña de RDS la genera AWS.
  - El backend construye `NP_DATABASE_URL` a partir del secreto de RDS (`NP_DATABASE_SECRET`).
- **IP del cliente y límites de frecuencia.** Una CloudFront Function sobrescribe `x-np-client-ip` con la IP real del visitante. CloudFront añade además `x-np-proxy-secret`. Es el mismo mecanismo que ya usa el proxy de Vercel, así que el backend no cambia.
- **Observabilidad.**
  - Los logs del backend van a CloudWatch Logs (`/neurophobia/backend`, 30 días) y no contienen datos personales.
  - Los logs de PostgreSQL solo registran las sentencias lentas.
  - Con `alarmEmail` se crean alarmas por correo (errores 5xx, sin tareas sanas, CPU, almacenamiento de RDS) y un presupuesto mensual.
- **Revisión automática.** `cdk synth` ejecuta las reglas *AWS Solutions* de cdk-nag. Cada excepción aceptada lleva su motivo escrito en el código.

## 2. Requisitos previos

| Herramienta | Versión | Comprobación |
| --- | --- | --- |
| AWS CLI | v2 | `aws --version` |
| Node.js | 20.19 o superior | `node --version` |
| Docker Desktop | en marcha | `docker info` |
| Session Manager plugin | solo para crear el administrador | `session-manager-plugin` |

No hace falta instalar AWS CDK de forma global: el script usa la versión fijada en `infra/aws/package.json`.

**Credenciales.** Necesitas un usuario o rol con permisos de administrador en la cuenta, porque `cdk bootstrap` crea roles de IAM.

- Con IAM Identity Center: `aws configure sso` y después `aws sso login`.
- Con claves de acceso: `aws configure`.

Comprueba la cuenta con `aws sts get-caller-identity`. No copies claves en archivos del repositorio.

NP_Front debe estar en `../NP_Front`, junto a NP_Back. Si está en otra carpeta, cambia `frontend.sourceDir`.

## 3. Parámetros

Copia el ejemplo y revísalo. `parameters.json` está en `.gitignore`.

```powershell
Copy-Item infra\aws\parameters.example.json infra\aws\parameters.json
```

| Parámetro | Ejemplo | Significado |
| --- | --- | --- |
| `projectName` | `neurophobia` | Prefijo de los nombres. Si lo cambias, cambian también los nombres de las pilas. |
| `account` | `""` | Cuenta de 12 dígitos. Si lo dejas vacío, se usa la de las credenciales actuales. |
| `region` | `us-east-1` | Región de AWS. |
| `alarmEmail` | `""` | Correo para las alarmas y el presupuesto. Si lo dejas vacío, no se crean. AWS envía un correo de confirmación que tienes que aceptar. |
| `monthlyBudgetUsd` | `60` | Límite del presupuesto: avisa al 80 % del gasto real y al 100 % del previsto. |
| `database.mode` | `rds` | `rds` crea la base de datos; `external` reutiliza Supabase u otra base. |
| `database.externalSecretName` | `neurophobia/database-url` | Secreto con `NP_DATABASE_URL` cuando `mode` es `external`. |
| `database.instanceClass` | `t4g.micro` | Tamaño de RDS. |
| `database.multiAz` | `false` | `true` duplica la base en otra zona (alta disponibilidad, y aproximadamente el doble de coste). |
| `database.deletionProtection` | `false` | `true` impide borrar la base, incluso con el script de borrado. |
| `backend.cpu` / `backend.memoryMiB` | `256` / `512` | 0,25 vCPU y 512 MiB por tarea. |
| `backend.desiredCount` | `1` | Número de tareas. Con `2` hay redundancia entre zonas. |
| `backend.cpuArchitecture` | `X86_64` | `ARM64` (Graviton) cuesta un 20 % menos, pero en un PC x86 la imagen se compila más despacio. |
| `backend.useSpot` | `false` | `true` usa Fargate Spot: unos 70 % más barato, pero AWS puede reiniciar la tarea. |
| `frontend.sourceDir` | `../NP_Front` | Carpeta de NP_Front, relativa a NP_Back. |

## 4. Desplegar (un comando)

Ejecuta el comando desde la carpeta NP_Back.

Windows (PowerShell):

```powershell
.\scripts\deploy-aws.ps1
```

Linux, macOS o Git Bash:

```bash
scripts/deploy-aws.sh
```

El script hace lo siguiente:

1. Comprueba las herramientas y las credenciales.
2. Compila NP_Front con `VITE_API_BASE_URL=/api/v1` y `VITE_USE_MOCKS=false`.
3. Ejecuta `cdk bootstrap`, que solo hace algo la primera vez.
4. Ejecuta `cdk deploy --all`.

Antes de crear roles o reglas de red, CDK muestra los cambios de seguridad y pide confirmación. Con `-Yes` (o `--yes` en Bash) no la pide.

La primera vez tarda unos 15–25 minutos, sobre todo por RDS y CloudFront. Al terminar muestra:

```text
Web:              https://dxxxxxxxxxxxx.cloudfront.net
API (Unity):      https://dxxxxxxxxxxxx.cloudfront.net/api/v1
Logs del backend: /neurophobia/backend
```

Las mismas salidas quedan en `infra/aws/outputs.json`, que no se versiona.

**Volver a desplegar** después de cambiar el código es el mismo comando. Se crea una imagen nueva, ECS la despliega sin cortar el servicio y las migraciones pendientes se aplican al arrancar.

**Comprobar el despliegue:**

1. `GET https://.../api/v1/health` debe devolver `200`.
2. `GET https://.../api/v1/health/ready` debe devolver `"database": "ok"`.
3. Prueba el registro, el inicio de sesión, la recarga de página y el cierre de sesión.

## 5. Crear el primer administrador

```powershell
.\scripts\aws-create-admin.ps1
```

El script abre una sesión de ECS Exec en el contenedor y ejecuta `python -m app.cli create-admin`. Este comando pide el nombre, el correo y la contraseña en la terminal. La contraseña no se pasa como argumento, así que no queda en ningún log ni en el historial.

## 6. Usar Supabase en lugar de RDS (opcional)

1. Pon `database.mode` a `"external"` en `parameters.json`.
2. Crea el secreto con la URI de Supabase (*Session pooler* 5432 o *Transaction pooler* 6543, con el esquema `postgresql+psycopg://` y `?sslmode=require`; consulta [DESPLIEGUE_VERCEL.md](DESPLIEGUE_VERCEL.md)). Escribe la URI en un archivo temporal **fuera del repositorio**, para que no quede en el historial, y bórralo al terminar:

   ```powershell
   aws secretsmanager create-secret --name neurophobia/database-url --secret-string file://C:/ruta/temporal/url.txt --region us-east-1
   Remove-Item C:/ruta/temporal/url.txt
   ```

3. Ejecuta `deploy-aws`. No se crea RDS, y la pila de datos solo contiene la red.

En este modo, el coste baja unos 14 USD al mes.

## 7. Cambiar la URL de la API en la app de Unity

El visor solo necesita la URL nueva. El contrato v1 y el emparejamiento no cambian.

1. En Unity, abre la escena y selecciona el objeto que tiene el componente `FastAPIClient` (`Assets/Scripts/Comunicacion/FastAPIClient.cs`).
2. En el Inspector, cambia **Base Url** de `http://localhost:8000` a la URL `Web` del despliegue (`https://dxxxx.cloudfront.net`), sin barra final. El cliente añade las rutas detrás. Si tu versión del cliente espera la base completa de la API, usa la salida `API (Unity)`, que termina en `/api/v1`.
3. Compila de nuevo para el visor. La URL es HTTPS, así que Android/Quest no necesita permitir tráfico HTTP.
4. Empareja de nuevo el visor desde la web (*Mis dispositivos*). Los tokens de dispositivo de Vercel no sirven en AWS, porque cada despliegue tiene su propia base de datos.

Si tienes un dominio propio, puedes añadirlo a CloudFront con un certificado de ACM en `us-east-1`. Esto está fuera de esta versión.

## 8. Coste mensual estimado

La estimación es para `us-east-1`, con precios bajo demanda, uso de prototipo académico (pocos usuarios) y la tarea encendida 24/7. Son precios de lista aproximados, no una factura: compruébalos en la [calculadora de precios de AWS](https://calculator.aws/) para tu región.

| Componente | Configuración | USD/mes aprox. |
| --- | --- | --- |
| ALB interno | 1 ALB, tráfico mínimo | 17 |
| ECS Fargate | 1 tarea de 0,25 vCPU y 0,5 GB (x86) | 9 |
| IPv4 pública de la tarea | 1 dirección | 3,7 |
| RDS PostgreSQL | db.t4g.micro, una zona, 20 GiB gp3 | 14 |
| Secrets Manager | 3 secretos | 1,2 |
| CloudFront + S3 | dentro del nivel gratuito permanente (1 TB y 10 M peticiones) | 0–1 |
| CloudWatch | logs, 5 alarmas, *flow logs* de rechazos | 1–2 |
| ECR | imágenes del backend | < 0,5 |
| **Total con RDS** | | **≈ 46–48** |
| **Total con Supabase** (`external`) | | **≈ 32–34** |

Cómo bajarlo:

- `backend.useSpot: true` deja Fargate en unos 3 USD.
- `ARM64` ahorra un 20 % adicional.
- Borra todo con `teardown-aws` cuando no lo uses: el coste es por hora.

Las cuentas nuevas de AWS suelen incluir créditos del nivel gratuito; revisa los tuyos en *Billing → Credits*. Al borrar el despliegue, la instantánea final de RDS sigue costando el almacenamiento (céntimos por GB) hasta que la borres.

## 9. Borrar el despliegue

```powershell
.\scripts\teardown-aws.ps1
```

El script pide que escribas el nombre del proyecto para confirmar. Después borra la pila de la aplicación, quita la protección de la pila de datos y la borra.

Quedan dos cosas:

- La **instantánea final de RDS** (*RDS → Snapshots*), por si necesitas recuperar los datos.
- La pila `CDKToolkit` del *bootstrap*. Otras aplicaciones de CDK pueden usarla; no la borres a mano.

## 10. Operación

- **Logs:** abre *CloudWatch → Log groups → `/neurophobia/backend`*, o ejecuta `aws logs tail /neurophobia/backend --follow`.
- **Migraciones:** se aplican solas en cada despliegue. Si una migración falla, la tarea no arranca, ECS vuelve a la versión anterior y el error aparece en los logs.
- **Rotar `NP_SECRET_KEY`:** cambia el valor en Secrets Manager y fuerza un despliegue nuevo del servicio (*ECS → Update service → Force new deployment*). Todas las sesiones web se cierran.
- **Rotar `NP_PROXY_SECRET`:** cambia el valor y vuelve a ejecutar `deploy-aws`, porque CloudFront lo lee al desplegar.
- **Ver los cambios antes de desplegar:** `cd infra/aws; npx cdk diff -c parameters=parameters.json`.

## 11. Límites conocidos

Son decisiones de coste para un prototipo; se pueden activar después.

- Sin AWS WAF (unos 6 USD al mes más reglas). El backend ya aplica sus propios límites por IP.
- Sin rotación automática de la contraseña de RDS. Se puede activar con endpoints de VPC o con un NAT.
- RDS en una sola zona (`multiAz: false`) y una sola tarea (`desiredCount: 1`).
- Dominio por defecto de CloudFront, sin dominio propio.
- Las tareas tienen IP pública (sin NAT), aunque solo aceptan tráfico del ALB.

## 12. Verificación de la plantilla (sin desplegar)

```powershell
cd infra\aws
npm ci
npm test                                                  # pruebas de las pilas y de las CloudFront Functions
npx cdk synth --strict -c parameters=parameters.example.json   # incluye cdk-nag AwsSolutions
```

`npx cdk synth` necesita que NP_Front esté compilado (`npm run build` en NP_Front). No necesita credenciales.

Opcionalmente puedes ejecutar `pip install cfn-lint` y después `cfn-lint cdk.out/*.template.json`.
