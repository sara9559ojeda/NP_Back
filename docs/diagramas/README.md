# Diagramas de NEUROPHOBIA — fichas para Visual Paradigm Online

Estas fichas describen, elemento por elemento, lo que va en cada diagrama para dibujarlo en **Visual Paradigm Online**. Salen del código de los tres repositorios:

- **NP_Back:** backend FastAPI + PostgreSQL.
- **NP_Front:** web React + TypeScript.
- **NPdefdef:** app de realidad virtual en Unity.

| Ficha | Tipo de diagrama en VP Online |
|---|---|
| [01_entidad_relacion.md](01_entidad_relacion.md) | *Entity Relationship Diagram* (ERD) |
| [02_clases_backend.md](02_clases_backend.md) | *Class Diagram* (UML) |
| [03_clases_unity.md](03_clases_unity.md) | *Class Diagram* (UML) |
| [04_componentes.md](04_componentes.md) | *Component Diagram* (UML) |
| [05_paquetes.md](05_paquetes.md) | *Package Diagram* (UML) |

## Criterios usados

- **Versión:** el código actual, que sigue el contrato `contrato-v1.1.0`. Ese contrato sigue pendiente de aprobación.
- **Diagrama entidad-relación:** tiene las 14 tablas reales de `app/db/models.py`, incluidas las técnicas. Tres relaciones no tienen clave foránea porque cruzan esquemas o son un libro de entrada; se dibujan como **relación lógica** (línea punteada con nota).
- **Diagrama de clases:** se hace uno para el backend y otro para Unity. La web no tiene clases (son componentes funcionales de React), así que aparece solo en los diagramas de componentes y de paquetes.
- **Unity:** se incluyen solo las clases propias del proyecto, sin los assets de terceros. Las carpetas de ajustes `NeuroPhobia_*` se agrupan en un paquete aparte.

## Importarlos ya dibujados (recomendado)

La carpeta [`drawio/`](drawio) tiene cada diagrama ya hecho en formato **draw.io**, que VP Online sabe importar:

| Archivo | Diagrama |
|---|---|
| `01_entidad_relacion.drawio` | Entidad-relación (notación pata de gallo) |
| `02a_clases_backend_entidades.drawio` | Clases del backend: entidades |
| `02b_clases_backend_logica.drawio` | Clases del backend: servicios, repositorios, IA y core |
| `03_clases_unity.drawio` | Clases de la app VR |
| `04a_componentes_sistema.drawio` | Componentes: vista general |
| `04b_componentes_internos.drawio` | Componentes internos de API, web y app VR |
| `05_paquetes.drawio` | Paquetes de los tres repositorios |

Pasos:

1. Descarga el archivo `.drawio` (en GitHub: abre el archivo y pulsa *Download raw file*).
2. En **VP Online**, abre o crea un diagrama y usa **File › Import** (o *Import* en la pantalla de inicio) y elige **draw.io**.
3. Selecciona el archivo. Si el selector solo acepta `.xml`, cambia la extensión de `.drawio` a `.xml`: el contenido es el mismo.
4. Ajusta lo que quieras: las cajas se pueden mover y las líneas se reenrutan solas.

Si la importación da problemas, hay dos alternativas:

- Abre el `.drawio` en https://app.diagrams.net y, desde ahí, usa *File › Export as › XML* (sin comprimir). Importa ese XML en VP Online.
- Usa los archivos de [`plantuml/`](plantuml): pega su contenido en el editor PlantUML de Visual Paradigm (https://www.visual-paradigm.com/features/plantuml-editor/) o, en Visual Paradigm Desktop, en *Tools › Import › PlantUML*.

Para regenerar los archivos después de cambiar el código: `python docs/diagramas/generar.py`.

## Cómo dibujarlos a mano en VP Online

1. **Diagram › New**, busca el tipo de la tabla de arriba y créalo.
2. **Clase:** añade la forma *Class*. Escribe los atributos con el formato `+ nombre : Tipo` y las operaciones con `+ nombre(param : Tipo) : Retorno`. El estereotipo (`«entity»`, `«service»`…) se pone en *Stereotypes* del panel de propiedades.
3. **Relación:** elige el conector de la paleta (*Association*, *Aggregation*, *Composition*, *Generalization*, *Realization*, *Dependency*). Las multiplicidades se ponen en los extremos del conector (doble clic sobre el extremo).
4. **ERD:** usa *Entity* y añade columnas con el botón **+**. Marca *PK* y escribe el tipo exacto. Las relaciones van con *One-to-Many* / *One-to-One* (notación pata de gallo). Al conectar, VP crea la columna FK automáticamente. Si la columna ya existe, bórrala para que no quede duplicada.
5. **Agrupar:** en ERD agrupa las tablas con *Package* (`identity` y `clinical`). En componentes y paquetes usa *Package* o *Subsystem*.

Visibilidad: `+` pública, `-` privada, `#` protegida. En Python lo que empieza por `_` se marca privado (`-`).
