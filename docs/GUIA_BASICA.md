# NEUROPHOBIA — Guía básica

Trabajo de grado de **Sara María Ojeda López**, Ingeniería de Software, Universidad Cooperativa de Colombia (Pasto, 2026).

## ¿Qué es?

NEUROPHOBIA es un prototipo académico de **realidad virtual para apoyar el tratamiento de la aracnofobia** (miedo a las arañas) mediante **exposición gradual**. El paciente usa unas gafas **Meta Quest** y recorre cinco niveles, cada uno con un poco más de exposición a arañas:

| Nivel | Nombre |
|---|---|
| 1 | Psicoeducación |
| 2 | Distancia segura |
| 3 | Aproximación progresiva |
| 4 | Contacto virtual |
| 5 | Desafío final |

Al terminar cada nivel, las gafas envían los resultados al servidor: malestar antes y después, eventos y mirada. El profesional de la salud los revisa desde la web, junto con una recomendación automática que todavía está **pendiente de validar** clínicamente. La decisión siempre es del profesional.

> No es un dispositivo médico ni sustituye a un terapeuta. Se usa con el acompañamiento de un profesional de la salud.

## Productos en línea

Todo funciona en **una sola dirección web**, alojada en AWS:

| Producto | Dirección | Para qué |
|---|---|---|
| **Web (frontend)** | https://d2jh1px5hj3b01.cloudfront.net | Información, registro, inicio de sesión y paneles del paciente, del profesional y del administrador |
| **API (backend)** | https://d2jh1px5hj3b01.cloudfront.net/api/v1 | Servicio al que se conectan la web y las gafas |
| Estado de la API | https://d2jh1px5hj3b01.cloudfront.net/api/v1/health | Comprueba que el servidor responde |
| **App VR (APK)** | Archivo para instalar en Meta Quest 2, 3 o 3S | Las sesiones de exposición |

Cómo está montado, en pocas palabras:

- **Amazon CloudFront** da la conexión segura (HTTPS).
- Detrás hay **un servidor EC2** que tiene la web, la API (Python, FastAPI) y la base de datos (PostgreSQL).
- Se hace una copia de seguridad diaria en S3.

## Roles

- **Visitante:** lee la información y se registra.
- **Paciente:** ve su progreso, vincula sus gafas y puede retirar su consentimiento.
- **Profesional de la salud:** ve a sus pacientes, sus sesiones y la recomendación, deja notas y decide el nivel inicial.
- **Administrador:** gestiona usuarios y asignaciones, y exporta datos anónimos. No ve datos clínicos.

## Cómo descargar e instalar el APK

> **Estado actual:** la web publicada **todavía no tiene un botón de descarga**. El APK está guardado de forma privada en AWS, y Sara comparte un **enlace temporal** con las personas autorizadas. Cuando se añada la descarga en la web, este apartado se actualizará.

1. **Activa el modo desarrollador** del Quest. En la app **Meta Horizon** del móvil: *Dispositivos → tu visor → Configuración del visor → Modo desarrollador*.
2. **Descarga el APK** (`neurophobia.apk`) en tu computador desde el enlace que te compartan.
3. **Instálalo.** Elige una de estas opciones:
   - **Opción fácil:** instala **SideQuest** en el computador, conecta el visor por USB, acepta el permiso dentro del visor y arrastra el APK a SideQuest.
   - **Opción técnica:** con `adb` (incluido en Android Platform Tools), ejecuta:

     ```
     adb install -r neurophobia.apk
     ```

4. **Ábrela** en el visor: *Biblioteca → Orígenes desconocidos → NeuroPhobia*.

## Primeros pasos

1. Entra en la web y **crea tu cuenta** de paciente.
2. El administrador te asigna un **profesional de la salud**.
3. En la web, ve a **«Mi visor»** y genera un **código de vinculación**.
4. Ponte las gafas, abre NeuroPhobia y escribe ese código. Las gafas quedan vinculadas a tu cuenta.
5. Haz la sesión. Al terminar cada nivel, los resultados aparecen en la web.

Puedes pausar o salir de forma segura en cualquier momento.

## Código fuente

| Parte | Repositorio |
|---|---|
| App VR (Unity 6, OpenXR) | https://github.com/sara9559ojeda/NPdefdef |
| Backend (FastAPI + PostgreSQL) | https://github.com/sara9559ojeda/NP_Back |
| Web (React + TypeScript) | https://github.com/sara9559ojeda/NP_Front |

Cada repositorio tiene en su README las instrucciones para instalarlo y desarrollarlo.
