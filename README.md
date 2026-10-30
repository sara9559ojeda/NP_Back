# NEUROPHOBIA — Backend

API REST del sistema NEUROPHOBIA, prototipo académico de realidad virtual para apoyar el tratamiento de la aracnofobia mediante exposición gradual. Trabajo de grado de **Sara María Ojeda López**, Ingeniería de Software, Universidad Cooperativa de Colombia (Pasto, 2026).

> NEUROPHOBIA no es un dispositivo médico ni sustituye a un terapeuta. Se usa con el acompañamiento de un profesional de la salud.

## Qué hace

- Cuentas y roles: paciente, profesional de la salud y administrador.
- Recepción de los registros de cada nivel que envía la app de realidad virtual (Meta Quest).
- Seguimiento del profesional: progreso de sus pacientes y notas.
- Módulo de IA: índice de tolerancia y recomendación al cerrar cada sesión. Primero una línea base de reglas; después, un modelo supervisado interpretable.

## Tecnologías

Python, FastAPI, PostgreSQL (con `JSONB` para los registros de sesión), Alembic y Docker. Arquitectura en capas: presentación, lógica de negocio, módulo de IA y acceso a datos.

## Contrato de la API

La especificación aprobada está en [`docs/api/CONTRATO_API_v1.md`](docs/api/CONTRATO_API_v1.md). **Este repositorio es su fuente**: la web y la app de realidad virtual guardan copias fijadas a una versión (`contrato-vX.Y.Z`).

## Repositorios relacionados

- App de realidad virtual (Unity): https://github.com/sara9559ojeda/NPdefdef
- Web (React + TypeScript): https://github.com/sara9559ojeda/NP_Front

## Puesta en marcha

Las instrucciones para levantarlo con Docker, ejecutar las pruebas y configurar las variables de entorno se añadirán junto con el código.
