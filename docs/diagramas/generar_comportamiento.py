"""Genera en draw.io los diagramas de despliegue, casos de uso y secuencia de NEUROPHOBIA.

Complementa a generar.py (estructura). Uso:  python docs/diagramas/generar_comportamiento.py
Salida: docs/diagramas/drawio/06_*.drawio … 10_*.drawio
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from generar import OUT, Drawio

BLUE = "fillColor=#7FD0F5;strokeColor=#000000;"
FONT = "fontSize=12;"


class Dr(Drawio):
    """Añade a Drawio aristas por puntos (para secuencia) y aristas entre celdas con estilo libre."""

    def link(self, s: str, t: str, style: str, label: str = "") -> str:
        cid = self.nid()
        c = ET.SubElement(self.root, "mxCell", id=cid, value=label, style="html=0;fontSize=11;" + style,
                          edge="1", parent="1", source=s, target=t)
        ET.SubElement(c, "mxGeometry", {"relative": "1", "as": "geometry"})
        return cid

    def arrow(self, x1, y1, x2, y2, label: str, style: str, points=()) -> None:
        cid = self.nid()
        c = ET.SubElement(self.root, "mxCell", id=cid, value=label, edge="1", parent="1",
                          style="html=0;fontSize=11;verticalAlign=bottom;" + style)
        g = ET.SubElement(c, "mxGeometry", {"relative": "1", "as": "geometry"})
        ET.SubElement(g, "mxPoint", {"x": f"{x1}", "y": f"{y1}", "as": "sourcePoint"})
        ET.SubElement(g, "mxPoint", {"x": f"{x2}", "y": f"{y2}", "as": "targetPoint"})
        if points:
            arr = ET.SubElement(g, "Array", {"as": "points"})
            for px, py in points:
                ET.SubElement(arr, "mxPoint", {"x": f"{px}", "y": f"{py}"})


def save(dr: Dr, file: str, title: str) -> None:
    dr.write(OUT / "drawio" / f"{file}.drawio", title)
    print("ok", file)


# ───────────────────────────── despliegue ─────────────────────────────

NODE = "shape=cube;whiteSpace=wrap;html=0;boundedLbl=1;backgroundOutline=1;darkOpacity=0.05;darkOpacity2=0.1;size=12;" \
       "verticalAlign=top;fontStyle=1;container=1;" + BLUE + FONT
COMP = "shape=component;align=center;spacingLeft=20;whiteSpace=wrap;html=0;fontStyle=1;fillColor=#FFFFFF;strokeColor=#000000;" + FONT
ACTOR = "shape=umlActor;verticalLabelPosition=bottom;verticalAlign=top;html=0;outlineConnect=0;" + BLUE + FONT
DASH = "dashed=1;endArrow=open;endSize=10;edgeStyle=orthogonalEdgeStyle;rounded=0;"


def despliegue() -> None:
    d = Dr()
    actor = d.vertex("Paciente", ACTOR, 20, 90, 30, 60)
    vr = d.vertex("«device»\nDispositivo VR (Meta Quest)", NODE, 240, 40, 420, 190)
    gafas = d.vertex("«component»\nGafasVR", COMP, 20, 50, 170, 50, vr)
    unity = d.vertex("«component»\nApp Unity", COMP, 220, 115, 170, 50, vr)
    fe = d.vertex("«executionEnvironment»\nFrontend (navegador)", NODE, 0, 300, 220, 170)
    interfaz = d.vertex("«component»\nInterfaz web (React)", COMP, 20, 70, 170, 50, fe)
    be = d.vertex("«device»\nServidor Backend", NODE, 240, 330, 520, 220)
    https = d.vertex("«component»\nServidor HTTPS (FastAPI)", COMP, 25, 55, 200, 50, be)
    ibd = d.vertex("«component»\nInterfaz BD (SQLAlchemy)", COMP, 25, 140, 200, 50, be)
    ia = d.vertex("«component»\nIA", COMP, 300, 140, 170, 50, be)
    bd = d.vertex("«device»\nServidor BD", NODE, 790, 190, 220, 160)
    pg = d.vertex("«component»\nPostgreSQL", COMP, 20, 60, 170, 50, bd)

    d.link(actor, gafas, "dashed=1;dashPattern=1 3;endArrow=open;", "Ingresa a la aplicación")
    d.link(unity, https, DASH, "HTTPS /api/v1/device")
    d.link(https, unity, DASH, "respuesta JSON")
    d.link(interfaz, https, DASH, "HTTPS /api/v1")
    d.link(https, ia, DASH, "«use»")
    d.link(https, ibd, DASH, "«use»")
    d.link(ibd, pg, "dashed=1;startArrow=open;endArrow=open;endSize=10;startSize=10;", "TCP / SQL")
    save(d, "06_despliegue", "NEUROPHOBIA - Diagrama de despliegue")


# ───────────────────────────── casos de uso ─────────────────────────────

UC = "ellipse;whiteSpace=wrap;html=0;fillColor=#FFFFFF;strokeColor=#000000;" + FONT
ASSOC = "endArrow=none;"
GEN = "endArrow=block;endFill=0;endSize=14;"


def casos_de_uso() -> None:
    d = Dr()
    d.vertex("Sistema VR (NEUROPHOBIA)", "rounded=0;whiteSpace=wrap;html=0;verticalAlign=top;fontSize=14;" + BLUE, 240, 0, 570, 700)
    adm = d.vertex("Administrador", ACTOR, 55, 40, 30, 60)
    pro = d.vertex("Profesional\nde la salud", ACTOR, 55, 210, 30, 60)
    pac = d.vertex("Paciente", ACTOR, 55, 400, 30, 60)
    ext = d.vertex("Usuario\nExterno", ACTOR, 55, 560, 30, 60)
    uc = {n: d.vertex(n, UC, x, y, 150, 62) for n, x, y in [
        ("Gestionar perfiles", 330, 60), ("Gestionar avance", 320, 200), ("Gestionar datos personales", 280, 360),
        ("Iniciar Sesión", 460, 410), ("Iniciar Terapia", 300, 470), ("Visualizar información del producto", 300, 555),
        ("Registrarse", 460, 630)]}
    d.link(pac, pro, GEN)
    d.link(pro, adm, GEN)
    for actor, names in ((adm, ["Gestionar perfiles"]),
                         (pro, ["Gestionar avance", "Gestionar datos personales", "Iniciar Sesión"]),
                         (pac, ["Gestionar datos personales", "Iniciar Sesión", "Iniciar Terapia"]),
                         (ext, ["Visualizar información del producto", "Registrarse"])):
        for n in names:
            d.link(actor, uc[n], ASSOC)
    save(d, "07_casos_de_uso", "NEUROPHOBIA - Diagrama de casos de uso")


# ───────────────────────────── secuencia ─────────────────────────────

LL = "shape=umlLifeline;perimeter=lifelinePerimeter;whiteSpace=wrap;html=0;container=0;collapsible=0;recursiveResize=0;" \
     "outlineConnect=0;size=44;" + BLUE + FONT
LL_ACTOR = LL + "participant=umlActor;verticalAlign=top;labelPosition=center;verticalLabelPosition=bottom;"
ACT = "html=0;points=[];perimeter=orthogonalPerimeter;" + BLUE
MSG = "endArrow=block;endFill=1;endSize=10;"
REPLY = "endArrow=open;endSize=10;dashed=1;"
FRAME = "shape=umlFrame;whiteSpace=wrap;html=0;width=50;height=24;fontStyle=1;fillColor=none;strokeColor=#000000;"
GAP, TOP, STEP = 190, 0, 44


def secuencia(file: str, title: str, parts: list[str], msgs: list[tuple], height: int, frames=()) -> None:
    """msgs: (desde, hasta, texto, 'call'|'reply') ; desde == hasta → mensaje a sí mismo.
    frames: (texto_operador, guarda1, fila_inicio, fila_fin, guarda2, fila_separador)."""
    d = Dr()
    xs = {}
    for i, p in enumerate(parts):
        x = i * GAP
        style = LL_ACTOR if i == 0 else LL
        w = 40 if i == 0 else 120
        d.vertex(p, style, x + (60 - w / 2), TOP, w, height)
        xs[p] = x + 60
    y0 = TOP + 90
    for k, (a, b, text, kind) in enumerate(msgs):
        y = y0 + k * STEP
        d.vertex("", ACT, xs[b] - 5, y - 4, 10, 30)
        if a == b:
            d.arrow(xs[a] + 5, y, xs[a] + 5, y + 18, text, MSG + "align=left;spacingLeft=4;",
                    points=[(xs[a] + 40, y), (xs[a] + 40, y + 18)])
        else:
            sx = xs[a] + (5 if xs[b] > xs[a] else -5)
            tx = xs[b] + (-5 if xs[b] > xs[a] else 5)
            d.arrow(sx, y, tx, y, text, MSG if kind == "call" else REPLY)
    for op, g1, r1, r2, g2, rsep in frames:
        fy = y0 + r1 * STEP - 30
        fh = (r2 - r1 + 1) * STEP + 20
        fx = xs[parts[0]] + 30
        fw = xs[parts[-1]] - fx + 70
        d.vertex(op, FRAME, fx, fy, fw, fh)
        d.vertex(g1, "text;html=0;fontSize=11;fontStyle=2;", fx + 55, fy, 220, 20)
        sy = y0 + rsep * STEP - 22
        d.arrow(fx, sy, fx + fw, sy, "", "endArrow=none;dashed=1;dashPattern=8 4;")
        d.vertex(g2, "text;html=0;fontSize=11;fontStyle=2;", fx + 6, sy, 220, 20)
    save(d, file, title)


def secuencias() -> None:
    secuencia("08_secuencia_iniciar_terapia", "Secuencia - Iniciar terapia (paciente)",
              ["Paciente", "Software VR (Unity)", "Backend", "Base de datos"],
              [("Paciente", "Software VR (Unity)", "Iniciar terapia", "call"),
               ("Software VR (Unity)", "Backend", "Envía métricas", "call"),
               ("Backend", "Base de datos", "Guarda métricas", "call"),
               ("Backend", "Backend", "Analiza datos", "call"),
               ("Backend", "Base de datos", "Guarda retroalimentación", "call"),
               ("Base de datos", "Backend", "Retroalimentación guardada", "reply")], 420)
    secuencia("09_secuencia_revisar_avance", "Secuencia - Revisar avance y anotar comentarios (profesional)",
              ["Profesional", "Interfaz", "Backend", "Base de datos"],
              [("Profesional", "Interfaz", "Revisar avance", "call"),
               ("Interfaz", "Base de datos", "Consultar retroalimentación", "call"),
               ("Base de datos", "Interfaz", "Retroalimentación", "reply"),
               ("Interfaz", "Interfaz", "Salir", "call"),
               ("Profesional", "Interfaz", "Anotar comentarios", "call"),
               ("Interfaz", "Backend", "Validar información", "call"),
               ("Backend", "Base de datos", "Guardar datos", "call"),
               ("Base de datos", "Backend", "Datos válidos", "reply"),
               ("Backend", "Interfaz", "Comentario anotado", "reply"),
               ("Interfaz", "Interfaz", "Salir", "call")], 560)
    secuencia("10_secuencia_iniciar_sesion", "Secuencia - Iniciar sesión (paciente)",
              ["Paciente", "Iniciar Sesión", "Interfaz de usuario", "Controlador", "Database"],
              [("Paciente", "Iniciar Sesión", "Ingresar credenciales", "call"),
               ("Iniciar Sesión", "Controlador", "Validar credenciales", "call"),
               ("Controlador", "Database", "Consultar credenciales", "call"),
               ("Database", "Controlador", "Credenciales correctas", "reply"),
               ("Controlador", "Interfaz de usuario", "Ingreso exitoso", "reply"),
               ("Interfaz de usuario", "Iniciar Sesión", "Salir", "call"),
               ("Paciente", "Iniciar Sesión", "Ingresar credenciales", "call"),
               ("Iniciar Sesión", "Controlador", "Validar credenciales", "call"),
               ("Controlador", "Database", "Consultar credenciales", "call"),
               ("Database", "Controlador", "Credenciales incorrectas", "reply"),
               ("Controlador", "Iniciar Sesión", "Datos incorrectos", "reply"),
               ("Iniciar Sesión", "Iniciar Sesión", "Salir", "call")], 660,
              frames=[("alt", "[credenciales correctas]", 1, 11, "[credenciales incorrectas]", 7)])
    secuencia("11_secuencia_editar_perfiles", "Secuencia - Editar perfiles (administrador)",
              ["Administrador", "Interfaz", "Controlador", "Base de datos"],
              [("Administrador", "Interfaz", "Editar perfiles", "call"),
               ("Interfaz", "Controlador", "Ingresar información", "call"),
               ("Controlador", "Base de datos", "Actualizar información", "call"),
               ("Base de datos", "Controlador", "Información válida", "reply"),
               ("Controlador", "Interfaz", "Información actualizada", "reply"),
               ("Interfaz", "Interfaz", "Salir", "call"),
               ("Administrador", "Interfaz", "Editar perfiles", "call"),
               ("Interfaz", "Controlador", "Ingresar información", "call"),
               ("Controlador", "Base de datos", "Actualizar información", "call"),
               ("Base de datos", "Controlador", "Información inválida", "reply"),
               ("Controlador", "Interfaz", "Datos incorrectos", "reply"),
               ("Interfaz", "Interfaz", "Salir", "call")], 660,
              frames=[("alt", "[información válida]", 1, 11, "[información inválida]", 7)])


if __name__ == "__main__":
    (OUT / "drawio").mkdir(exist_ok=True)
    despliegue()
    casos_de_uso()
    secuencias()
