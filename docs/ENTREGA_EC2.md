# Entrega al servidor EC2 existente

Este procedimiento está preparado para revisión en la máquina con acceso autorizado. No se ha ejecutado en AWS desde este PC. No ejecutar `deploy.py deploy`: aprovisiona infraestructura y no sustituye este procedimiento de actualización.

## Artefactos locales

Después de las pruebas y los commits, construir `neurophobia-api:academic-delivery` con Docker y la web con `npm run build`. Ejecutar desde NP_Back:

```powershell
.venv/Scripts/python.exe scripts/prepare_ec2_delivery.py
```

Salida ignorada por Git: `infra/ec2/.build/delivery`. Incluye imagen Docker, web, herramientas de operación y `delivery.json` con revisiones Git, ID inmutable de imagen y SHA-256. No contiene claves ni la base de datos. Conservar el APK y `release.json` de Unity por separado; sigue pendiente de validación en gafas.

## Preparación en la máquina autorizada

1. Verificar el informe y la instancia concreta existente en Ohio. No crear otra pila ni migrar a ECS/RDS. Revisar espacio libre local y remoto.
2. Comparar todos los SHA-256 después de transferir los artefactos por el mecanismo privado ya autorizado (S3 privado y SSM). No publicar el bucket. `sha256sum -c SHA256SUMS` verifica el contenido.
3. Con SSM, comprobar copia diaria reciente y prueba de restauración; conservar además copia de `/opt/neurophobia/frontend` y de `/opt/neurophobia/infra/nginx.conf`. Revisar configuración nginx efectiva y sus diferencias antes de sustituir archivos.
4. Descomprimir herramientas en un directorio de revisión, no encima del servidor activo. Cargar `image.tar` con `docker load -i image.tar`. Comparar el ID con `delivery.json`.
5. Si se activa Groq, escribir directamente en `/opt/neurophobia/config/groq.env` las variables de `IA_SESIONES.md`, como root, modo 600. No poner la clave en comandos registrados ni informes. Usar solo Groq Free y datos ficticios. Si el archivo no existe, la integración permanece deshabilitada.

## Actualización del backend

Revisar `update_runtime.py` antes de ejecutarlo como root con `--image sha256:<ID completo verificado>`.

El script crea una copia PostgreSQL local privada, aplica exclusivamente hasta migración `0004`, concede permisos sobre las tablas clínicas, conserva el contenedor anterior con nombre `np-api-rollback-<fecha>` y arranca la nueva API. Monta `/opt/neurophobia/releases` como solo lectura. Si la API no queda lista, intenta restaurar el contenedor anterior. No borra el volumen PostgreSQL ni hace downgrade automático de la base. Las adiciones de `0004` son compatibles con la imagen anterior.

La copia local no sustituye la copia externa: comprobar su legibilidad con `pg_restore --list` y conservar el respaldo de S3. Antes de ejecutar, confirmar que siguen existiendo `np-internal`, `np-api-network`, `np_owner`, `np_app`, `owner.env` y `runtime.env`. El script se ha revisado y compilado localmente; su operación sobre esta instancia sigue pendiente.

Verificar `/api/v1/health/ready`, acceso con cada rol, aislamiento entre pacientes, vinculación y sesión ficticia completa. Comprobar que el usuario `np_app` accede a la tabla nueva. No identificar la revisión desplegada únicamente por `health.version`, que puede coincidir entre commits.

## Actualización de la web y nginx

Extraer `frontend.tar.gz` en un directorio nuevo. Conservar la web anterior; renombrar el directorio nuevo a `/opt/neurophobia/frontend` durante la ventana de actualización. La web no depende de archivos de desarrollo ni de `mockServiceWorker.js`.

Copiar la configuración revisada de nginx y `security-headers.conf` a `/opt/neurophobia/infra`. Conservar la inyección privada del proxy existente: no publicar ni copiar su secreto a un informe. La plantilla `nginx.conf` requiere sustituir `__PROXY_SECRET__` con ese mismo valor mediante el proceso privado de configuración. No ejecutar `setup.py` a ciegas para actualizar esta instancia.

Ejecutar `nginx -t` antes de recargar. Verificar en la URL pública la guía `/instalar`, CSP, cabeceras y que una ruta `.apk` inexistente devuelve 404. El APK se entrega exclusivamente por el endpoint autenticado, nunca mediante el fallback HTML de la SPA. Revisar navegador tras desplegar: CSP puede descubrir fuentes o conexiones adicionales de una configuración distinta.

## APK y prueba física

El build nuevo usa HTTPS de CloudFront y produce `release.json` con SHA-256 y revisión. Instalar primero mediante USB por la persona responsable. En Quest verificar: arranque, controles reales, nivel 5, pausa/salida, vinculación, envío y consulta del resultado en Refugio y web. Verificar firma y ausencia de `debuggable` con las herramientas Android.

Solo después de esa prueba se pueden marcar `headsetTested=true` y `distributionReady=true` en una copia del manifiesto y colocar ambos archivos en `/opt/neurophobia/releases`, legibles por UID 10001. No modificar el APK tras calcular el hash. Las claves de firma permanecen fuera de Git y del paquete web.

## Regreso a la versión anterior

Si falla el recorrido funcional aunque readiness responda, detener la nueva API, conservarla para diagnóstico y devolver al nombre `np-api` el contenedor anterior. Iniciar ese contenedor. Recuperar la carpeta frontend y la configuración nginx guardadas, ejecutar `nginx -t` y recargar. No restaurar una base antigua ni eliminar columnas de forma automática: eso puede perder sesiones nuevas. Registrar exactamente los IDs de imagen y las revisiones usadas.

## Costos

No se añade ningún servicio AWS. El servidor, disco, copias y tráfico existentes siguen consumiendo créditos. El informe externo indica saldo 99,63 USD y ausencia de alertas; verificar consumo y configurar avisos desde la máquina autorizada. El contador Groq limita solicitudes y no controla la facturación de AWS.
