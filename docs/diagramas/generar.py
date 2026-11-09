"""Genera los diagramas de NEUROPHOBIA en formato draw.io (.drawio) y PlantUML (.puml).

Visual Paradigm Online importa archivos draw.io; los .puml sirven para el editor PlantUML de
Visual Paradigm o para Visual Paradigm Desktop (Tools > Import > PlantUML).

Uso:  python docs/diagramas/generar.py   (sin dependencias externas)
Salida: docs/diagramas/drawio/*.drawio y docs/diagramas/plantuml/*.puml
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

OUT = Path(__file__).resolve().parent
CHAR_W = 6.6  # ancho medio de un carácter a 11 px
ROW_H = 16
HEAD_H = 34

# ─────────────────────────────── modelo ───────────────────────────────


@dataclass
class Box:
    name: str
    stereo: str = ""
    attrs: list[str] = field(default_factory=list)
    ops: list[str] = field(default_factory=list)
    kind: str = "class"  # class | table | component | package | db | note
    group: str = ""  # contenedor (paquete o componente padre)


@dataclass
class Edge:
    src: str
    dst: str
    kind: str  # assoc comp agg gen real dep er er1 erlog
    label: str = ""
    m1: str = ""
    m2: str = ""


@dataclass
class Diagram:
    file: str
    title: str
    rows: list[list[str]]  # disposición en cuadrícula (nombres de cajas por fila)
    boxes: dict[str, Box]
    edges: list[Edge]
    groups: dict[str, str] = field(default_factory=dict)  # grupo -> estereotipo
    puml_kind: str = "class"


def boxes(*items: Box) -> dict[str, Box]:
    return {b.name: b for b in items}


# ─────────────────────────────── draw.io ───────────────────────────────

EDGE_STYLE = {
    "assoc": "endArrow=none;",
    "comp": "startArrow=diamondThin;startFill=1;startSize=14;endArrow=none;",
    "agg": "startArrow=diamondThin;startFill=0;startSize=14;endArrow=none;",
    "gen": "endArrow=block;endFill=0;endSize=12;",
    "real": "endArrow=block;endFill=0;endSize=12;dashed=1;",
    "dep": "endArrow=open;endFill=0;dashed=1;",
    "er": "startArrow=ERmandOne;endArrow=ERzeroToMany;startFill=0;endFill=0;",
    "er1": "startArrow=ERmandOne;endArrow=ERzeroToOne;startFill=0;endFill=0;",
    "er01": "startArrow=ERzeroToOne;endArrow=ERzeroToMany;startFill=0;endFill=0;",
    "erlog": "startArrow=ERmandOne;endArrow=ERzeroToMany;startFill=0;endFill=0;dashed=1;",
    "erlog1": "startArrow=ERmandOne;endArrow=ERzeroToOne;startFill=0;endFill=0;dashed=1;",
}

BOX_STYLE = {
    "class": "swimlane;fontStyle=1;align=center;verticalAlign=top;childLayout=stackLayout;horizontal=1;"
    "startSize={h};horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;"
    "marginBottom=0;whiteSpace=wrap;html=0;fillColor=#dae8fc;strokeColor=#6c8ebf;swimlaneFillColor=#ffffff;",
    "table": "swimlane;fontStyle=1;align=center;verticalAlign=top;childLayout=stackLayout;horizontal=1;"
    "startSize={h};horizontalStack=0;resizeParent=1;resizeParentMax=0;resizeLast=0;collapsible=0;"
    "marginBottom=0;whiteSpace=wrap;html=0;fillColor=#d5e8d4;strokeColor=#82b366;swimlaneFillColor=#ffffff;",
    "component": "shape=component;align=left;spacingLeft=36;verticalAlign=top;spacingTop=6;whiteSpace=wrap;"
    "html=0;fillColor=#fff2cc;strokeColor=#d6b656;",
    "db": "shape=cylinder3;whiteSpace=wrap;html=0;boundedLbl=1;backgroundOutline=1;size=12;"
    "fillColor=#f8cecc;strokeColor=#b85450;",
    "package": "shape=folder;fontStyle=1;spacingTop=10;tabWidth=60;tabHeight=16;tabPosition=left;html=0;"
    "whiteSpace=wrap;verticalAlign=top;align=left;spacingLeft=8;fillColor=#e1d5e7;strokeColor=#9673a6;",
    "note": "shape=note;whiteSpace=wrap;html=0;size=14;verticalAlign=top;align=left;spacingLeft=6;"
    "fillColor=#ffffff;strokeColor=#999999;fontSize=10;",
}
TEXT_STYLE = (
    "text;strokeColor=none;fillColor=none;align=left;verticalAlign=top;spacingLeft=4;spacingRight=4;"
    "overflow=hidden;rotatable=0;points=[[0,0.5],[1,0.5]];portConstraint=eastwest;whiteSpace=wrap;html=0;fontSize=11;"
)
LINE_STYLE = "line;strokeWidth=1;fillColor=none;align=left;verticalAlign=middle;spacingTop=-1;spacingLeft=3;spacingRight=3;rotatable=0;labelPosition=right;points=[];portConstraint=eastwest;"
GROUP_STYLE = (
    "shape=folder;fontStyle=1;tabWidth=140;tabHeight=22;tabPosition=left;html=0;whiteSpace=wrap;verticalAlign=top;"
    "align=left;spacingLeft=10;spacingTop=2;fillColor=none;strokeColor=#666666;dashed=0;fontSize=13;container=1;"
)


def header(b: Box) -> str:
    return f"«{b.stereo}»\n{b.name}" if b.stereo else b.name


def size(b: Box) -> tuple[float, float]:
    lines = [header(b).split("\n")[-1], f"«{b.stereo}»"] + b.attrs + b.ops
    w = max(140, min(560, max(len(x) for x in lines) * CHAR_W + 24))
    if b.kind in ("class", "table"):
        h = HEAD_H + (len(b.attrs) or 1) * ROW_H + 8 + (len(b.ops) * ROW_H + 8 if b.ops else 0)
    elif b.kind == "package":
        w = max(w, 160)
        h = 50 + len(b.attrs) * ROW_H
    elif b.kind == "db":
        w, h = max(w, 160), 90 + len(b.attrs) * ROW_H
    else:
        h = 44 + len(b.attrs) * ROW_H
    return w, h


class Drawio:
    def __init__(self) -> None:
        self.root = ET.Element("root")
        ET.SubElement(self.root, "mxCell", id="0")
        ET.SubElement(self.root, "mxCell", id="1", parent="0")
        self.n = 0

    def nid(self) -> str:
        self.n += 1
        return f"c{self.n}"

    def vertex(self, value: str, style: str, x, y, w, h, parent="1") -> str:
        cid = self.nid()
        c = ET.SubElement(self.root, "mxCell", id=cid, value=value, style=style, vertex="1", parent=parent)
        ET.SubElement(c, "mxGeometry", {"x": f"{x:.0f}", "y": f"{y:.0f}", "width": f"{w:.0f}", "height": f"{h:.0f}", "as": "geometry"})
        return cid

    def box(self, b: Box, x, y, w, h, parent="1") -> str:
        if b.kind in ("class", "table"):
            head = HEAD_H if b.stereo else 26
            cid = self.vertex(header(b), BOX_STYLE[b.kind].format(h=head), x, y, w, h, parent)
            ah = (len(b.attrs) or 1) * ROW_H + 8
            self.vertex("\n".join(b.attrs), TEXT_STYLE, 0, head, w, ah, cid)
            if b.ops:
                self.vertex("", LINE_STYLE, 0, head + ah, w, 8, cid)
                self.vertex("\n".join(b.ops), TEXT_STYLE, 0, head + ah + 8, w, len(b.ops) * ROW_H + 8, cid)
            return cid
        text = header(b) + ("\n" + "\n".join(b.attrs) if b.attrs else "")
        return self.vertex(text, BOX_STYLE[b.kind], x, y, w, h, parent)

    def edge(self, e: Edge, s: str, t: str) -> None:
        cid = self.nid()
        style = "edgeStyle=orthogonalEdgeStyle;rounded=1;html=0;fontSize=10;jumpStyle=arc;" + EDGE_STYLE[e.kind]
        c = ET.SubElement(self.root, "mxCell", id=cid, value=e.label, style=style, edge="1", parent="1", source=s, target=t)
        ET.SubElement(c, "mxGeometry", {"relative": "1", "as": "geometry"})
        for text, x in ((e.m1, "-0.85"), (e.m2, "0.85")):
            if text:
                lid = self.nid()
                lc = ET.SubElement(self.root, "mxCell", id=lid, value=text, vertex="1", connectable="0", parent=cid,
                                   style="edgeLabel;resizable=0;html=0;fontSize=10;labelBackgroundColor=#ffffff;")
                g = ET.SubElement(lc, "mxGeometry", {"x": x, "relative": "1", "as": "geometry"})
                ET.SubElement(g, "mxPoint", {"as": "offset", "y": "-10"})

    def write(self, path: Path, name: str) -> None:
        mxfile = ET.Element("mxfile", host="neurophobia-generator", type="device")
        diagram = ET.SubElement(mxfile, "diagram", id="d1", name=name)
        model = ET.SubElement(diagram, "mxGraphModel", dx="1400", dy="900", grid="1", gridSize="10", guides="1",
                              tooltips="1", connect="1", arrows="1", fold="1", page="0", pageScale="1",
                              pageWidth="1600", pageHeight="1200", math="0", shadow="0")
        model.append(self.root)
        ET.indent(mxfile)
        path.write_text(ET.tostring(mxfile, encoding="unicode"), encoding="utf-8")


GAP_X, GAP_Y = 70, 70


def render_drawio(d: Diagram) -> None:
    dr = Drawio()
    ids: dict[str, str] = {}
    sizes = {n: size(b) for n, b in d.boxes.items()}

    if d.groups:
        # Cada fila de `rows` es un grupo: ["grupo", caja, caja, ...]; las cajas del grupo se reparten en columnas.
        y = 0.0
        for row in d.rows:
            gname, members = row[0], row[1:]
            per = 4 if len(members) > 4 else len(members)
            lines = [members[i:i + per] for i in range(0, len(members), per)]
            inner_w = max(sum(sizes[m][0] for m in ln) + GAP_X * (len(ln) - 1) for ln in lines)
            inner_h = sum(max(sizes[m][1] for m in ln) for ln in lines) + GAP_Y * (len(lines) - 1)
            gw, gh = inner_w + 60, inner_h + 70
            label = f"«{d.groups[gname]}» {gname}" if d.groups[gname] else gname
            gid = dr.vertex(label, GROUP_STYLE, 0, y, gw, gh)
            yy = 45.0
            for ln in lines:
                xx = 30.0
                for m in ln:
                    w, h = sizes[m]
                    ids[m] = dr.box(d.boxes[m], xx, yy, w, h, gid)
                    xx += w + GAP_X
                yy += max(sizes[m][1] for m in ln) + GAP_Y
            y += gh + 60
    else:
        ncols = max(len(r) for r in d.rows)
        col_w = [0.0] * ncols
        for r in d.rows:
            for i, n in enumerate(r):
                if n:
                    col_w[i] = max(col_w[i], sizes[n][0])
        y = 0.0
        for r in d.rows:
            x = 0.0
            row_h = max((sizes[n][1] for n in r if n), default=0)
            for i in range(ncols):
                n = r[i] if i < len(r) else ""
                if n:
                    w, h = sizes[n]
                    ids[n] = dr.box(d.boxes[n], x, y, w, h)
                x += col_w[i] + GAP_X
            y += row_h + GAP_Y

    for e in d.edges:
        dr.edge(e, ids[e.src], ids[e.dst])
    (OUT / "drawio").mkdir(exist_ok=True)
    dr.write(OUT / "drawio" / f"{d.file}.drawio", d.title)


# ─────────────────────────────── PlantUML ───────────────────────────────

PUML_ARROW = {
    "assoc": "--", "comp": "*--", "agg": "o--", "gen": "--|>", "real": "..|>", "dep": "..>",
    "er": "||--o{", "er1": "||--o|", "er01": "|o--o{", "erlog": "||..o{", "erlog1": "||..o|",
}


def pid(name: str) -> str:
    return "".join(ch if ch.isalnum() else "_" for ch in name)


def render_puml(d: Diagram) -> None:
    out = [f"@startuml {d.file}", f"title {d.title}", "skinparam classAttributeIconSize 0",
           "skinparam linetype ortho", "hide empty members", ""]
    if d.puml_kind == "er":
        out.insert(3, "hide circle")

    def emit(b: Box, indent: str) -> None:
        st = f" <<{b.stereo}>>" if b.stereo else ""
        if b.kind in ("class", "table"):
            kw = "entity" if b.kind == "table" else ("interface" if b.stereo == "interface" else
                                                    "enum" if b.stereo == "enumeration" else "class")
            st = "" if kw in ("interface", "enum") else st
            out.append(f'{indent}{kw} "{b.name}" as {pid(b.name)}{st} {{')
            out.extend(f"{indent}  {a}" for a in b.attrs)
            if b.ops:
                out.append(f"{indent}  --")
                out.extend(f"{indent}  {o}" for o in b.ops)
            out.append(f"{indent}}}")
        elif b.kind == "component":
            out.append(f'{indent}component "{b.name}" as {pid(b.name)}{st}')
            if b.attrs:
                out.append(f"{indent}note bottom of {pid(b.name)}\n" + "\n".join(f"{indent}  {a}" for a in b.attrs) + f"\n{indent}end note")
        elif b.kind == "db":
            out.append(f'{indent}database "{b.name}" as {pid(b.name)}{st}')
        elif b.kind == "package":
            out.append(f'{indent}package "{b.name}" as {pid(b.name)}{st} {{\n{indent}}}')
        elif b.kind == "note":
            out.append(f'{indent}note "{b.name}\\n' + "\\n".join(b.attrs) + f'" as {pid(b.name)}')

    if d.groups:
        for row in d.rows:
            g, members = row[0], row[1:]
            st = f" <<{d.groups[g]}>>" if d.groups[g] else ""
            out.append(f'package "{g}"{st} {{')
            for m in members:
                emit(d.boxes[m], "  ")
            out.append("}")
    else:
        for r in d.rows:
            for n in r:
                if n:
                    emit(d.boxes[n], "")
    out.append("")
    for e in d.edges:
        a = PUML_ARROW[e.kind]
        m1 = f' "{e.m1}"' if e.m1 else ""
        m2 = f' "{e.m2}"' if e.m2 else ""
        lab = f" : {e.label}" if e.label else ""
        out.append(f"{pid(e.src)}{m1} {a}{m2} {pid(e.dst)}{lab}")
    out.append("@enduml\n")
    (OUT / "plantuml").mkdir(exist_ok=True)
    (OUT / "plantuml" / f"{d.file}.puml").write_text("\n".join(out), encoding="utf-8")


# ─────────────────────────────── diagramas ───────────────────────────────


def er() -> Diagram:
    T = lambda name, cols, schema: Box(name, schema, cols, kind="table")  # noqa: E731
    I, C = "identity", "clinical"
    b = boxes(
        T("users", ["PK id : uuid", "U  email : varchar(320)", "   password_hash : text [N]", "   role : varchar(16)  {patient|professional|admin}",
                    "   active : boolean", "   created_at : timestamptz", "   updated_at : timestamptz [N]", "   withdrawn_at : timestamptz [N]"], I),
        T("personal_data", ["PK,FK user_id : uuid", "   full_name : varchar(200)", "   updated_at : timestamptz"], I),
        T("consents", ["PK id : uuid", "FK user_id : uuid", "   consent_version : varchar(64)", "   granted_at : timestamptz", "   withdrawn_at : timestamptz [N]"], I),
        T("identity_links", ["PK,FK user_id : uuid", "U  pseudonym_id : uuid  (sin FK)"], I),
        T("assignments", ["PK id : uuid", "FK professional_user_id : uuid", "FK patient_user_id : uuid", "   active : boolean",
                          "   created_at : timestamptz", "   ended_at : timestamptz [N]"], I),
        T("refresh_tokens", ["PK id : uuid", "FK user_id : uuid", "   family_id : uuid", "U  token_hash : varchar(64)",
                             "   created_at : timestamptz", "   expires_at : timestamptz", "   revoked_at : timestamptz [N]"], I),
        T("rate_limit_events", ["PK id : bigint", "   key_hash : varchar(64)", "   occurred_at : timestamptz"], I),
        T("patients", ["PK pseudonym_id : uuid", "   allowed_start_level : smallint {1..5}", "   plan_updated_at : timestamptz [N]",
                       "   phobia_grade : smallint {1..5} [N]", "   phobia_grade_updated_at : timestamptz [N]",
                       "   retain_until : timestamptz [N]", "   created_at : timestamptz"], C),
        T("pairing_codes", ["PK id : uuid", "FK pseudonym_id : uuid", "U  code_hash : varchar(64)", "   created_at : timestamptz",
                            "   expires_at : timestamptz", "   used_at : timestamptz [N]"], C),
        T("devices", ["PK id : uuid", "FK pseudonym_id : uuid", "   model : varchar(32)", "   app_version : varchar(32)",
                      "U  token_hash : varchar(64)", "   paired_at : timestamptz", "   last_seen_at : timestamptz [N]", "   revoked_at : timestamptz [N]"], C),
        T("sessions", ["PK id : uuid", "FK pseudonym_id : uuid", "FK device_id : uuid [N]", "   has_start : boolean", "   has_end : boolean",
                       "   started_at : timestamptz [N]", "   ended_at : timestamptz [N]", "   phobia_grade : smallint [N]",
                       "   test_session : boolean [N]", "   app_version : varchar(32) [N]", "   device_model : varchar(32) [N]",
                       "   end_reason : varchar(32) [N]", "   level_reached : smallint [N]", "   total_duration_seconds : float [N]",
                       "   raw : jsonb", "   created_at : timestamptz"], C),
        T("level_records", ["PK id : uuid", "FK session_id : uuid", "   level : smallint", "   attempt : smallint", "   outcome : varchar(32)",
                            "   criterion_met : boolean", "   started_at : timestamptz", "   ended_at : timestamptz", "   permanence_seconds : float",
                            "   min_distance_m : float [N]", "   avoidance_count : integer", "   payload : jsonb", "   received_at : timestamptz"], C),
        T("analyses", ["PK,FK session_id : uuid", "PK method : varchar(32)", "   method_version : varchar(16)", "   tolerance_index : float {0..1}",
                       "   recommendation : varchar(16) {advance|repeat|step_back}", "   basis : jsonb", "   clinical_status : varchar(32)",
                       "   created_at : timestamptz"], C),
        T("notes", ["PK id : uuid", "FK pseudonym_id : uuid", "FK session_id : uuid [N]", "   author_user_id : uuid  (sin FK)", "   text : text",
                    "   created_at : timestamptz", "   edited_at : timestamptz [N]"], C),
        T("inbound_records", ["PK record_id : uuid", "   pseudonym_id : uuid  (sin FK)", "   device_id : uuid [N]  (sin FK)",
                              "   session_id : uuid  (sin FK)", "   type : varchar(16)", "   schema_version : smallint",
                              "   content_hash : varchar(64)", "   received_at : timestamptz"], C),
        Box("Nota", "", ["Líneas punteadas = relaciones lógicas sin FK",
                         "(cruzan los esquemas identity y clinical).",
                         "Retirar el consentimiento borra personal_data",
                         "e identity_links: los datos clínicos quedan anónimos."], kind="note"),
    )
    rows = [
        ["personal_data", "consents", "refresh_tokens", "rate_limit_events", "Nota"],
        ["identity_links", "users", "assignments", "", ""],
        ["patients", "pairing_codes", "devices", "notes", ""],
        ["inbound_records", "sessions", "level_records", "analyses", ""],
    ]
    E = Edge
    edges = [
        E("users", "personal_data", "er1"), E("users", "consents", "er"), E("users", "identity_links", "er1"),
        E("users", "assignments", "er", "professional"), E("users", "assignments", "er", "patient"),
        E("users", "refresh_tokens", "er"), E("patients", "pairing_codes", "er"), E("patients", "devices", "er"),
        E("patients", "sessions", "er"), E("devices", "sessions", "er01"), E("sessions", "level_records", "er"),
        E("sessions", "analyses", "er"), E("patients", "notes", "er"), E("sessions", "notes", "er01"),
        E("patients", "identity_links", "erlog1", "«lógica» pseudonym_id"), E("users", "notes", "erlog", "«lógica» author_user_id"),
        E("sessions", "inbound_records", "erlog", "«lógica» session_id"),
    ]
    return Diagram("01_entidad_relacion", "NEUROPHOBIA - Diagrama entidad-relación", rows, b, edges, puml_kind="er")


def clases_backend_entidades() -> Diagram:
    E = lambda n, a: Box(n, "entity", a)  # noqa: E731
    b = boxes(
        Box("Base", "DeclarativeBase", ["+ metadata : MetaData"]),
        E("User", ["+ id : UUID", "+ email : str", "+ password_hash : str [0..1]", "+ role : str", "+ active : bool",
                   "+ created_at : datetime", "+ updated_at : datetime [0..1]", "+ withdrawn_at : datetime [0..1]"]),
        E("PersonalData", ["+ user_id : UUID", "+ full_name : str", "+ updated_at : datetime"]),
        E("Consent", ["+ id : UUID", "+ user_id : UUID", "+ consent_version : str", "+ granted_at : datetime", "+ withdrawn_at : datetime [0..1]"]),
        E("IdentityLink", ["+ user_id : UUID", "+ pseudonym_id : UUID"]),
        E("Assignment", ["+ id : UUID", "+ professional_user_id : UUID", "+ patient_user_id : UUID", "+ active : bool",
                         "+ created_at : datetime", "+ ended_at : datetime [0..1]"]),
        E("RefreshToken", ["+ id : UUID", "+ user_id : UUID", "+ family_id : UUID", "+ token_hash : str", "+ created_at : datetime",
                           "+ expires_at : datetime", "+ revoked_at : datetime [0..1]"]),
        E("RateLimitEvent", ["+ id : int", "+ key_hash : str", "+ occurred_at : datetime"]),
        E("Patient", ["+ pseudonym_id : UUID", "+ allowed_start_level : int", "+ plan_updated_at : datetime [0..1]",
                      "+ phobia_grade : int [0..1]", "+ phobia_grade_updated_at : datetime [0..1]", "+ retain_until : datetime [0..1]",
                      "+ created_at : datetime"]),
        E("PairingCode", ["+ id : UUID", "+ pseudonym_id : UUID", "+ code_hash : str", "+ created_at : datetime",
                          "+ expires_at : datetime", "+ used_at : datetime [0..1]"]),
        E("Device", ["+ id : UUID", "+ pseudonym_id : UUID", "+ model : str", "+ app_version : str", "+ token_hash : str",
                     "+ paired_at : datetime", "+ last_seen_at : datetime [0..1]", "+ revoked_at : datetime [0..1]"]),
        E("TherapySession", ["+ id : UUID", "+ pseudonym_id : UUID", "+ device_id : UUID [0..1]", "+ has_start : bool", "+ has_end : bool",
                             "+ started_at : datetime [0..1]", "+ ended_at : datetime [0..1]", "+ phobia_grade : int [0..1]",
                             "+ test_session : bool [0..1]", "+ app_version : str [0..1]", "+ device_model : str [0..1]",
                             "+ end_reason : str [0..1]", "+ level_reached : int [0..1]", "+ total_duration_seconds : float [0..1]",
                             "+ raw : dict", "+ created_at : datetime"]),
        E("LevelRecord", ["+ id : UUID", "+ session_id : UUID", "+ level : int", "+ attempt : int", "+ outcome : str",
                          "+ criterion_met : bool", "+ started_at : datetime", "+ ended_at : datetime", "+ permanence_seconds : float",
                          "+ min_distance_m : float [0..1]", "+ avoidance_count : int", "+ payload : dict", "+ received_at : datetime"]),
        E("Analysis", ["+ session_id : UUID", "+ method : str", "+ method_version : str", "+ tolerance_index : float",
                       "+ recommendation : str", "+ basis : list", "+ clinical_status : str", "+ created_at : datetime"]),
        E("Note", ["+ id : UUID", "+ pseudonym_id : UUID", "+ session_id : UUID [0..1]", "+ author_user_id : UUID", "+ text : str",
                   "+ created_at : datetime", "+ edited_at : datetime [0..1]"]),
        E("InboundRecord", ["+ record_id : UUID", "+ pseudonym_id : UUID", "+ device_id : UUID [0..1]", "+ session_id : UUID",
                            "+ type : str", "+ schema_version : int", "+ content_hash : str", "+ received_at : datetime"]),
    )
    rows = [
        ["PersonalData", "Consent", "RefreshToken", "RateLimitEvent", "Base"],
        ["IdentityLink", "User", "Assignment", "", ""],
        ["Patient", "PairingCode", "Device", "Note", ""],
        ["InboundRecord", "TherapySession", "LevelRecord", "Analysis", ""],
    ]
    X = Edge
    edges = [
        X("User", "PersonalData", "comp", "", "1", "0..1"), X("User", "Consent", "comp", "", "1", "0..*"),
        X("User", "IdentityLink", "comp", "", "1", "0..1"), X("User", "RefreshToken", "comp", "", "1", "0..*"),
        X("User", "Assignment", "assoc", "professional", "1", "0..*"), X("User", "Assignment", "assoc", "patient", "1", "0..*"),
        X("IdentityLink", "Patient", "dep", "«logical» pseudonym_id", "0..1", "1"),
        X("Patient", "PairingCode", "comp", "", "1", "0..*"), X("Patient", "Device", "comp", "", "1", "0..*"),
        X("Patient", "TherapySession", "comp", "", "1", "0..*"), X("Patient", "Note", "comp", "", "1", "0..*"),
        X("Device", "TherapySession", "assoc", "", "0..1", "0..*"), X("TherapySession", "LevelRecord", "comp", "", "1", "0..*"),
        X("TherapySession", "Analysis", "comp", "", "1", "0..*"), X("TherapySession", "Note", "assoc", "", "0..1", "0..*"),
        X("Note", "User", "dep", "«logical» author", "0..*", "1"),
        X("InboundRecord", "TherapySession", "dep", "«logical» session_id", "0..*", "1"),
    ]
    return Diagram("02a_clases_backend_entidades", "NP_Back - Clases (entidades del ORM, todas heredan de Base)", rows, b, edges)


def clases_backend_logica() -> Diagram:
    S = lambda n, ops: Box(n, "service", [], ops)  # noqa: E731
    b = boxes(
        S("AuthService", ["+ register(data : RegisterIn, ip : str) : UUID", "+ login(email : str, password : str, ip : str) : IssuedTokens",
                          "+ refresh(token : str) : IssuedTokens", "+ logout(token : str) : void",
                          "+ create_account(email, password, role, full_name) : UUID", "+ ensure_patient_link(user_id : UUID) : UUID",
                          "- _issue(user_id, role, family_id) : IssuedTokens"]),
        S("AccountsService", ["+ get_me(actor : Actor) : MeOut", "+ patch_me(actor : Actor, data : MePatch) : MeOut",
                              "+ change_password(actor : Actor, current : str, new : str) : void", "+ withdraw_consent(actor : Actor) : void",
                              "+ change_email(user : User, email : str, now : datetime) : void"]),
        S("AdminService", ["+ list_users(page, role, active, q) : AdminUserPage", "+ get_user(user_id) : AdminUserOut",
                           "+ create_user(data : AdminUserCreate) : AdminUserOut", "+ patch_user(user_id, data : AdminUserPatch) : AdminUserOut",
                           "+ reset_password(user_id, temporary_password) : void", "+ list_assignments(page, professional_id) : AssignmentPage",
                           "+ create_assignment(professional_id, patient_id) : AssignmentOut", "+ delete_assignment(assignment_id) : void",
                           "+ analysis_dataset() : dict", "+ dataset_to_csv(dataset : dict) : str"]),
        S("PairingService", ["+ create_code(pseudonym : UUID) : PairingCodeOut", "+ pair(data : PairIn, ip : str) : PairOut",
                             "+ authenticate_device(token : str) : DeviceActor", "+ list_devices(pseudonym) : DevicePage",
                             "+ revoke_device(pseudonym, device_id) : void"]),
        S("RecordsService", ["+ ingest(device : DeviceActor, body : dict) : RecordResult", "+ parse_envelope(body) : RecordEnvelope",
                             "+ content_hash(body : dict) : str", "+ device_context(device : DeviceActor) : DeviceContext",
                             "- _store(...) : str", "- _duplicate_or_conflict(...) : str"]),
        S("TrackingService", ["+ own_pseudonym(actor : Actor) : UUID", "+ assigned_pseudonym(actor, patient_id) : UUID",
                              "+ progress(pseudonym) : ProgressOut", "+ list_sessions(pseudonym, page) : SessionPage",
                              "+ session_detail(pseudonym, session_id, with_notes) : SessionDetail", "+ my_patients(actor, page) : PatientPage",
                              "+ set_plan(patient_id, pseudonym, level : int) : PlanOut", "+ list_notes(pseudonym, page, session_id) : NotePage",
                              "+ add_note(actor, pseudonym, text, session_id) : NoteCreated", "+ edit_note(actor, pseudonym, note_id, text) : NoteOut"]),
        S("TherapyService", ["+ set_phobia_grade(pseudonym, grade : int) : PhobiaGradeOut", "+ sync_phobia_grade_from_session(pseudonym, grade, at) : void",
                             "+ therapy_state(pseudonym) : TherapyStateOut", "+ device_session(device, session_id) : DeviceSessionOut",
                             "+ feedback_page(pseudonym, page) : FeedbackPage", "+ unpair(device : DeviceActor) : void"]),
        S("AnalysisService", ["+ refresh_analysis(session : TherapySession) : void", "+ feedback_for(session : TherapySession) : FeedbackOut"]),
        Box("Actor", "dataclass", ["+ user_id : UUID", "+ role : str"]),
        Box("DeviceActor", "dataclass", ["+ device_id : UUID", "+ pseudonym_id : UUID"]),
        Box("IssuedTokens", "dataclass", ["+ access_token : str", "+ expires_in : int", "+ refresh_token : str", "+ user_id : UUID", "+ role : str"]),
        Box("IdentityRepository", "repository", [], ["+ get_user(user_id) : User", "+ get_user_by_email(email) : User", "+ add_user(...) : User",
                                                     "+ set_full_name(user_id, name)", "+ add_consent / withdraw_consents(...)",
                                                     "+ get_pseudonym(user_id) : UUID", "+ add_link / delete_link(...)",
                                                     "+ add_assignment / list_assignments(...)", "+ is_assigned(prof_id, patient_id) : bool",
                                                     "+ add_refresh_token / revoke_family(...)"]),
        Box("ClinicalRepository", "repository", [], ["+ add_patient() / get_patient(pseudonym_id) : Patient", "+ add_pairing_code / get_pairing_code(...)",
                                                     "+ add_device / get_device_by_token_hash(...)", "+ try_add_inbound / get_inbound(...)",
                                                     "+ lock_or_create_session(session_id, pseudonym_id)", "+ list_sessions / progress_sessions(...)",
                                                     "+ add_level_record / level_records(...)", "+ upsert_analysis / analyses_for(...)",
                                                     "+ add_note / list_notes / get_note(...)", "+ export_rows(method)"]),
        Box("SessionAnalyzer", "interface", ["+ method : str", "+ method_version : str"], ["+ analyze(features : SessionFeatures) : AnalysisResult [0..1]"]),
        Box("RulesBaselineAnalyzer", "", ["- config : dict"], ["+ analyze(features : SessionFeatures) : AnalysisResult [0..1]", "- _effect(score : float) : Effect"]),
        Box("AnalyzerRegistry", "utility", [], ["+ get_analyzer(method : str) : SessionAnalyzer"]),
        Box("FeatureExtractor", "utility", [], ["+ level_features(payload : dict) : LevelFeatures", "+ session_features(...) : SessionFeatures"]),
        Box("SessionFeatures", "dataclass", ["+ phobia_grade : int [0..1]", "+ level_reached : int [0..1]", "+ end_reason : str [0..1]", "+ levels : LevelFeatures [*]"]),
        Box("LevelFeatures", "dataclass", ["+ level : int", "+ attempt : int", "+ outcome : str", "+ criterion_met : bool", "+ permanence_seconds : float",
                                           "+ avoidance_count : int", "+ min_distance_m : float [0..1]", "+ suds_before : int [0..1]",
                                           "+ suds_after : int [0..1]", "+ ended_at_epoch : float"]),
        Box("AnalysisResult", "dataclass", ["+ method : str", "+ method_version : str", "+ tolerance_index : float", "+ recommendation : Recommendation",
                                            "+ basis : BasisItem [*]", "+ clinical_status : str"]),
        Box("BasisItem", "dataclass", ["+ feature : str", "+ value : float", "+ effect : Effect"]),
        Box("Recommendation", "enumeration", ["advance", "repeat", "step_back"]),
        Box("Effect", "enumeration", ["favorable", "unfavorable", "neutral"]),
        Box("Settings", "BaseSettings", ["+ database_url : SecretStr", "+ secret_key : SecretStr", "+ cors_origin : str", "+ access_token_minutes : int = 15",
                                         "+ refresh_token_days : int = 7", "+ pairing_code_minutes : int = 10", "+ ai_method : str"]),
        Box("ApiError", "Exception", ["+ status : int", "+ code : str", "+ detail : str [0..1]", "+ errors : list [0..1]"]),
        Box("PostgresWindowLimiter", "", [], ["+ count(key, window) : int", "+ hit(key, window)", "+ check_and_hit(key, limit, window)", "+ ensure_below(key, limit, window)"]),
    )
    rows = [
        ["AuthService", "AccountsService", "AdminService", "PairingService"],
        ["Actor", "DeviceActor", "IssuedTokens", "PostgresWindowLimiter"],
        ["TrackingService", "TherapyService", "RecordsService", "AnalysisService"],
        ["IdentityRepository", "ClinicalRepository", "AnalyzerRegistry", "FeatureExtractor"],
        ["Settings", "ApiError", "SessionAnalyzer", "SessionFeatures"],
        ["", "Recommendation", "RulesBaselineAnalyzer", "LevelFeatures"],
        ["", "Effect", "AnalysisResult", "BasisItem"],
    ]
    D = lambda a, c, l="«use»": Edge(a, c, "dep", l)  # noqa: E731
    edges = [
        Edge("RulesBaselineAnalyzer", "SessionAnalyzer", "real"),
        Edge("SessionFeatures", "LevelFeatures", "comp", "", "1", "0..*"),
        Edge("AnalysisResult", "BasisItem", "comp", "", "1", "0..*"),
        Edge("AnalysisResult", "Recommendation", "assoc"), Edge("BasisItem", "Effect", "assoc"),
        D("AnalyzerRegistry", "SessionAnalyzer", "«create»"),
        D("AnalysisService", "AnalyzerRegistry"), D("AnalysisService", "FeatureExtractor"), D("AnalysisService", "ClinicalRepository"),
        D("RecordsService", "AnalysisService"), D("RecordsService", "TherapyService"), D("RecordsService", "ClinicalRepository"),
        D("AuthService", "IdentityRepository"), D("AuthService", "ClinicalRepository"), D("AuthService", "PostgresWindowLimiter"),
        D("AuthService", "IssuedTokens", "«create»"),
        D("AccountsService", "IdentityRepository"), D("AdminService", "AuthService"), D("AdminService", "AccountsService"),
        D("AdminService", "IdentityRepository"), D("PairingService", "ClinicalRepository"), D("PairingService", "PostgresWindowLimiter"),
        D("PairingService", "DeviceActor", "«create»"), D("TrackingService", "ClinicalRepository"), D("TrackingService", "IdentityRepository"),
        D("TherapyService", "ClinicalRepository"), D("TrackingService", "Actor"), D("AccountsService", "Actor"),
        D("RecordsService", "DeviceActor"), D("FeatureExtractor", "SessionFeatures", "«create»"),
        D("RulesBaselineAnalyzer", "AnalysisResult", "«create»"),
    ]
    return Diagram("02b_clases_backend_logica", "NP_Back - Clases (servicios, repositorios, IA y core)", rows, b, edges)


def clases_unity() -> Diagram:
    M = lambda n, a, o=(), st="": Box(n, st, list(a), list(o))  # noqa: E731
    b = boxes(
        Box("MonoBehaviour", "library UnityEngine"),
        M("SessionManager", ["+ Instance : SessionManager {static}", "+ SessionId : string", "+ CurrentLevel : int", "+ PhobiaGrade : int",
                             "- report : SessionReport", "- pendingPost : LevelMetrics", "- apiClient : FastAPIClient"],
          ["+ StartSession(phobiaGrade : int, testSession : bool)", "+ AddLevelMetrics(metrics : LevelMetrics)", "+ RegisterLevelRetry(level : int)",
           "+ CurrentAttempt(level : int) : int", "+ RecordSudsBefore(level : int, value : int)", "+ RecordSudsAfter(level : int, value : int)",
           "+ PostPendingLevel()", "+ EndSession(endReason : string)", "+ GetReport() : SessionReport", "+ ResolveInitialLevel(phobiaGrade : int) : int"], "singleton"),
        M("LevelManager", ["+ Instance : LevelManager {static}"], ["+ LoadLevel(level : int)", "+ UnlockNextLevel()",
                                                                    "+ OnLevelComplete(level : int, metrics : LevelMetrics)"], "singleton"),
        M("GameStateManager", ["+ CurrentState : GameState {static}", "+ OnStateChanged : Action<GameState> {static}"], ["+ SetState(state : GameState) {static}"]),
        Box("GameState", "enumeration", ["MENU", "PLAYING", "PAUSED", "BREATHING", "LEVEL_COMPLETE", "SESSION_END"]),
        M("FastAPIClient", ["- baseUrl : string", "- timeoutSeconds : int = 10", "- outbox : RecordOutbox", "- cachedContext : DeviceContextDto"],
          ["+ Pair(code : string, onDone) : IEnumerator", "+ Unpair(onDone) : IEnumerator", "+ RefreshContext(onDone) : IEnumerator",
           "+ PutPhobiaGrade(grade : int) : IEnumerator", "+ PostSessionStart(sessionId, phobiaGrade, testSession) : IEnumerator",
           "+ PostLevelMetrics(sessionId, level, metrics) : IEnumerator", "+ PostSessionEnd(sessionId, report, endReason) : IEnumerator",
           "+ AllowedStartLevel() : int", "+ SyncStatusText() : string"]),
        M("DeviceRecordMapper", [], ["+ SessionStart(recordId, sessionId, startedUtc, phobiaGrade, ...) : string",
                                     "+ LevelRecord(recordId, sessionId, metrics, attempt, endedUtc) : string",
                                     "+ SessionEnd(recordId, sessionId, endedUtc, endReason, ...) : string",
                                     "+ ResolveOutcome(metrics : LevelMetrics) : string", "+ LevelReached(report : SessionReport) : int"], "utility"),
        M("RecordOutbox", ["+ OutboxDir : string", "+ QuarantineDir : string"],
          ["+ Enqueue(owner, type, recordId, json) : string", "+ Pending(owner) : List<string>", "+ Apply(path : string, action : OutboxAction)",
           "+ Classify(httpStatus : long) : OutboxAction {static}", "+ RetryDelaySeconds(failures, retryAfter) : double {static}"]),
        Box("OutboxAction", "enumeration", ["Delete", "Quarantine", "NeedsPairing", "Retry"]),
        M("NeuroPhobiaJson", ["- sb : StringBuilder"], ["+ BeginObject() : NeuroPhobiaJson", "+ Prop(name, value) : NeuroPhobiaJson", "+ ToString() : string"]),
        M("DeviceContextDto", ["+ allowedStartLevel : int", "+ phobiaGrade : int", "+ recommendation : RecommendationDto"], ["+ RecommendationText() : string"], "DTO"),
        M("RecommendationDto", ["+ value : string", "+ method : string", "+ clinicalStatus : string"], (), "DTO"),
        M("MetricsCollector", ["+ level : int", "+ player : Transform", "- gazeTimeOnSpider : float", "- avoidanceAttempts : int",
                               "- proximityMin : float", "- handContactDuration : float"],
          ["+ RegisterTaskCompletion(taskId : string)", "+ SetSpiders(spiders : AranaController[])", "+ RegisterBreathingActivation()",
           "+ RegisterHandWithdrawal()", "+ AddHandContactTime(seconds : float)", "+ BuildMetrics(passed : bool) : LevelMetrics"]),
        M("SessionReport", ["+ sessionId : string", "+ phobiaGrade : int", "+ totalDuration : float", "+ levelMetrics : List<LevelMetrics>",
                            "+ timestamp : string", "+ testSession : bool"], (), "Serializable"),
        M("LevelMetrics", ["+ level : int", "+ gazeTimeOnSpider : float", "+ avoidanceAttempts : int", "+ proximityMin : float",
                           "+ levelPassed : bool", "+ levelAttempts : int", "+ handContactDuration : float", "+ outcome : string",
                           "+ distanceSamples : List<float>", "+ events : List<LevelEvent>", "+ suds : List<SudsEntry>"], (), "Serializable"),
        M("LevelEvent", ["+ t : float", "+ type : string", "+ value : float"], (), "Serializable"),
        M("SudsEntry", ["+ phase : string", "+ value : int", "+ at : float"], (), "Serializable"),
        M("TaskManager", ["- completedTasks : HashSet<string>"], ["+ IsCompleted(id : string) : bool", "+ CompleteTask(taskId : string)"]),
        Box("IPhobiaStimulus", "interface", [], ["+ Pause()", "+ Resume()", "+ GetDistanceToPlayer() : float", "+ SetMovementPattern(p : MovementPattern)"]),
        M("AranaController", ["+ defaultPattern : MovementPattern", "+ player : Transform", "+ moveSpeed : float", "- paused : bool"],
          ["+ Pause()", "+ Resume()", "+ GetDistanceToPlayer() : float", "+ SetMovementPattern(p : MovementPattern)"]),
        Box("MovementPattern", "enumeration", ["IDLE", "SLOW_PATROL", "HAND_CRAWL", "FREE_ROAM"]),
        M("GlobalSessionUI", [], ["+ CompleteLevel(level : int) {static}", "+ OfferRepeat(level : int, message : string) : bool {static}",
                                  "+ ShowSessionSummary() {static}"]),
        M("NeuroPhobiaMainMenuModern", ["(consentimiento, grado de fobia, emparejamiento)"]),
        M("Level1SequentialGazeFlow", ["- cards : List<GameObject>", "- nextSceneName : string"], (), "Nivel 1"),
        M("NeuroPhobiaLevel2StableGaze", ["+ metricsCollector : MetricsCollector"], (), "Nivel 2"),
        M("Level3ProgressControllerV2", ["+ metricsCollector : MetricsCollector"], ["+ RegisterCheckpoint(order : int)"], "Nivel 3"),
        M("NPLevel4Controller", ["+ spiderPatrol : NPNaturalSpiderPatrol"], (), "Nivel 4"),
        M("Level4ContactTimer", ["+ metricsCollector : MetricsCollector", "- contactSeconds : float"], (), "Nivel 4"),
        M("NPLevel5Controller", ["+ spiderPatrols : NPNaturalSpiderPatrol[]"], ["+ LoadMenu()", "+ RestartLevel()"], "Nivel 5"),
        M("Level5DomesticTaskManager", ["+ metricsCollector : MetricsCollector"], ["+ RegisterTask(taskId : string)"], "Nivel 5"),
        M("NPNaturalSpiderPatrol", ["(patrulla de arañas, niveles 4 y 5)"]),
    )
    rows = [
        ["NeuroPhobiaMainMenuModern", "GameStateManager", "GameState", "LevelManager", "MonoBehaviour"],
        ["GlobalSessionUI", "SessionManager", "FastAPIClient", "RecordOutbox", "OutboxAction"],
        ["SessionReport", "LevelMetrics", "DeviceRecordMapper", "NeuroPhobiaJson", "DeviceContextDto"],
        ["LevelEvent", "SudsEntry", "MetricsCollector", "TaskManager", "RecommendationDto"],
        ["IPhobiaStimulus", "AranaController", "MovementPattern", "NPNaturalSpiderPatrol", ""],
        ["Level1SequentialGazeFlow", "NeuroPhobiaLevel2StableGaze", "Level3ProgressControllerV2", "Level4ContactTimer", "NPLevel4Controller"],
        ["Level5DomesticTaskManager", "NPLevel5Controller", "", "", ""],
    ]
    D = lambda a, c, l="«use»": Edge(a, c, "dep", l)  # noqa: E731
    edges = [
        Edge("AranaController", "IPhobiaStimulus", "real"), Edge("AranaController", "MovementPattern", "assoc"),
        Edge("SessionManager", "SessionReport", "comp", "", "1", "1"), Edge("SessionReport", "LevelMetrics", "comp", "", "1", "0..*"),
        Edge("LevelMetrics", "LevelEvent", "comp", "", "1", "0..*"), Edge("LevelMetrics", "SudsEntry", "comp", "", "1", "0..*"),
        Edge("SessionManager", "FastAPIClient", "assoc", "apiClient", "1", "1"), Edge("FastAPIClient", "RecordOutbox", "comp", "", "1", "1"),
        Edge("FastAPIClient", "DeviceContextDto", "assoc", "caché", "1", "0..1"), Edge("DeviceContextDto", "RecommendationDto", "comp", "", "1", "1"),
        D("RecordOutbox", "OutboxAction"), D("FastAPIClient", "DeviceRecordMapper"), D("DeviceRecordMapper", "NeuroPhobiaJson", "«create»"),
        D("MetricsCollector", "LevelMetrics", "«create»"), Edge("MetricsCollector", "AranaController", "assoc", "", "1", "0..*"),
        Edge("GameStateManager", "GameState", "assoc"), D("GameStateManager", "AranaController", "pausa / reanuda"),
        D("LevelManager", "SessionManager"), D("TaskManager", "MetricsCollector"),
        D("NeuroPhobiaMainMenuModern", "SessionManager"), D("NeuroPhobiaMainMenuModern", "FastAPIClient"),
        D("GlobalSessionUI", "SessionManager"), D("GlobalSessionUI", "MetricsCollector"),
        Edge("NeuroPhobiaLevel2StableGaze", "MetricsCollector", "assoc", "", "1", "1"),
        Edge("Level3ProgressControllerV2", "MetricsCollector", "assoc", "", "1", "1"),
        Edge("Level4ContactTimer", "MetricsCollector", "assoc", "", "1", "1"),
        Edge("Level5DomesticTaskManager", "MetricsCollector", "assoc", "", "1", "1"),
        D("Level3ProgressControllerV2", "SessionManager"), D("Level4ContactTimer", "SessionManager"),
        D("Level5DomesticTaskManager", "SessionManager"), D("NeuroPhobiaLevel2StableGaze", "SessionManager"),
        D("Level1SequentialGazeFlow", "GlobalSessionUI", "CompleteLevel"), D("NPLevel4Controller", "GlobalSessionUI", "CompleteLevel"),
        Edge("NPLevel4Controller", "NPNaturalSpiderPatrol", "assoc", "", "1", "1"),
        Edge("NPLevel5Controller", "NPNaturalSpiderPatrol", "agg", "", "1", "1..*"),
        Edge("SessionManager", "MonoBehaviour", "gen"), Edge("FastAPIClient", "MonoBehaviour", "gen"),
        Edge("LevelManager", "MonoBehaviour", "gen"), Edge("GameStateManager", "MonoBehaviour", "gen"),
    ]
    return Diagram("03_clases_unity", "NPdefdef (Unity) - Clases principales (los MonoBehaviour heredan de UnityEngine.MonoBehaviour)", rows, b, edges)


def componentes_sistema() -> Diagram:
    C = lambda n, st, a: Box(n, st, a, kind="component")  # noqa: E731
    b = boxes(
        C("App VR NEUROPHOBIA", "application", ["Unity 6000.3 · OpenXR · XR Toolkit", "APK Meta Quest 2/3/3S", "(repo NPdefdef)"]),
        Box("Almacenamiento local del visor", "artifact", ["outbox/ (RecordOutbox)", "device_context.json"], kind="note"),
        C("Web NEUROPHOBIA", "application", ["React + TypeScript (Vite) · SPA", "(repo NP_Front)"]),
        C("Proxy web", "component", ["Vercel: api/proxy.mjs", "AWS: CloudFront /api/v1/*", "añade x-np-proxy-secret, x-np-client-ip"]),
        C("API NEUROPHOBIA", "service", ["FastAPI · Python 3.12 · Docker", "/api/v1 (contrato v1.1.0)", "(repo NP_Back)"]),
        C("Módulo de IA", "component", ["app/ai · rules-baseline", "interfaz SessionAnalyzer"]),
        Box("PostgreSQL 17", "database", ["esquemas identity y clinical"], kind="db"),
    )
    rows = [["App VR NEUROPHOBIA", "", "Web NEUROPHOBIA"], ["Almacenamiento local del visor", "API NEUROPHOBIA", "Proxy web"],
            ["", "Módulo de IA", "PostgreSQL 17"]]
    D = lambda a, c, l: Edge(a, c, "dep", l)  # noqa: E731
    edges = [
        D("App VR NEUROPHOBIA", "API NEUROPHOBIA", "IDeviceAPI /api/v1/device (HTTPS, token de dispositivo)"),
        D("App VR NEUROPHOBIA", "Almacenamiento local del visor", "«use» archivos"),
        D("Web NEUROPHOBIA", "Proxy web", "IProxy /api/v1/* (mismo origen)"),
        D("Proxy web", "API NEUROPHOBIA", "IWebAPI /api/v1 (JWT + cookie refresh)"),
        D("API NEUROPHOBIA", "Módulo de IA", "SessionAnalyzer"),
        D("API NEUROPHOBIA", "PostgreSQL 17", "SQL (SQLAlchemy + Alembic)"),
    ]
    return Diagram("04a_componentes_sistema", "NEUROPHOBIA - Diagrama de componentes (vista general)", rows, b, edges, puml_kind="component")


def componentes_internos() -> Diagram:
    C = lambda n, a, g: Box(n, "component", a, kind="component", group=g)  # noqa: E731
    BK, WB, VR = "API NEUROPHOBIA (NP_Back)", "Web NEUROPHOBIA (NP_Front)", "App VR NEUROPHOBIA (NPdefdef)"
    items = [
        C("Routers HTTP", ["api/routes: auth, me, patients,", "admin, device, public, health"], BK),
        C("Autenticación y permisos", ["api/deps: current_actor,", "require_roles, current_device"], BK),
        C("Servicio de cuentas", ["services: auth, accounts, admin"], BK),
        C("Servicio de emparejamiento", ["services: pairing"], BK),
        C("Servicio de registros del visor", ["services: records"], BK),
        C("Servicio de seguimiento", ["services: tracking, therapy"], BK),
        C("Servicio de análisis", ["services: analysis"], BK),
        C("IA (SessionAnalyzer)", ["app/ai: rules-baseline"], BK),
        C("Repositorio identity", ["repositories/identity"], BK),
        C("Repositorio clinical", ["repositories/clinical"], BK),
        C("ORM y sesión de BD", ["app/db: models, session"], BK),
        C("Core", ["config, errors, security,", "ratelimit, logging, pagination"], BK),
        C("Enrutador", ["App.tsx (React Router)"], WB),
        C("Contexto de autenticación", ["auth: AuthProvider, RequireRole"], WB),
        C("Páginas", ["public, patient, professional,", "admin, cuenta, errores"], WB),
        C("Componentes de presentación", ["Layout, Clinical, therapy, ui"], WB),
        C("Hooks", ["useApi, usePaged"], WB),
        C("Cliente de API", ["api: client, endpoints, adapters"], WB),
        C("Textos i18n", ["es.json"], WB),
        C("Simulador MSW", ["mocks (solo desarrollo)"], WB),
        C("Menú principal", ["NeuroPhobiaMainMenuModern"], VR),
        C("Gestión de sesión", ["SessionManager, LevelManager,", "GameStateManager"], VR),
        C("Niveles 1-5", ["controladores por escena"], VR),
        C("Métricas", ["MetricsCollector, TaskManager,", "SessionReport, LevelMetrics"], VR),
        C("Estímulo (arañas)", ["AranaController, NPNaturalSpiderPatrol"], VR),
        C("UI de sesión", ["GlobalSessionUI, BreathingGuide, HUD"], VR),
        C("Cliente API Unity", ["FastAPIClient, DeviceRecordMapper"], VR),
        C("Bandeja de salida", ["RecordOutbox"], VR),
        C("Entrada XR / escritorio", ["XRBootstrap, ControlModeSelector"], VR),
    ]
    b = boxes(*items)
    rows = [[BK] + [i.name for i in items if i.group == BK], [WB] + [i.name for i in items if i.group == WB],
            [VR] + [i.name for i in items if i.group == VR]]
    D = lambda a, c, l="«use»": Edge(a, c, "dep", l)  # noqa: E731
    edges = [
        D("Routers HTTP", "Autenticación y permisos"), D("Routers HTTP", "Servicio de cuentas"), D("Routers HTTP", "Servicio de emparejamiento"),
        D("Routers HTTP", "Servicio de registros del visor"), D("Routers HTTP", "Servicio de seguimiento"),
        D("Autenticación y permisos", "Repositorio identity"), D("Servicio de cuentas", "Repositorio identity"),
        D("Servicio de emparejamiento", "Repositorio clinical"), D("Servicio de registros del visor", "Servicio de análisis"),
        D("Servicio de registros del visor", "Repositorio clinical"), D("Servicio de seguimiento", "Repositorio clinical"),
        D("Servicio de análisis", "IA (SessionAnalyzer)"), D("Repositorio identity", "ORM y sesión de BD"),
        D("Repositorio clinical", "ORM y sesión de BD"), D("ORM y sesión de BD", "Core"),
        D("Enrutador", "Páginas"), D("Enrutador", "Contexto de autenticación"), D("Páginas", "Componentes de presentación"),
        D("Páginas", "Hooks"), D("Páginas", "Textos i18n"), D("Hooks", "Cliente de API"), D("Contexto de autenticación", "Cliente de API"),
        D("Simulador MSW", "Cliente de API", "simula IWebAPI"),
        D("Menú principal", "Gestión de sesión"), D("Menú principal", "Cliente API Unity"), D("Niveles 1-5", "Gestión de sesión"),
        D("Niveles 1-5", "Métricas"), D("Niveles 1-5", "Estímulo (arañas)"), D("Niveles 1-5", "UI de sesión"),
        D("Gestión de sesión", "Cliente API Unity"), D("Cliente API Unity", "Bandeja de salida"), D("Niveles 1-5", "Entrada XR / escritorio"),
        D("Cliente de API", "Routers HTTP", "IWebAPI vía proxy"), D("Cliente API Unity", "Routers HTTP", "IDeviceAPI"),
    ]
    return Diagram("04b_componentes_internos", "NEUROPHOBIA - Componentes internos de cada aplicación", rows, b, edges,
                   groups={BK: "subsystem", WB: "subsystem", VR: "subsystem"}, puml_kind="component")


def paquetes() -> Diagram:
    P = lambda n, a, g, st="": Box(n, st, a, kind="package", group=g)  # noqa: E731
    BK, WB, VR = "NP_Back", "NP_Front", "NPdefdef"
    items = [
        P("main / cli", ["arranque FastAPI y comandos"], BK), P("api.routes", ["auth, me, patients, admin,", "device, public, health"], BK),
        P("api.deps", ["autenticación y roles"], BK), P("services", ["auth, accounts, admin, pairing,", "records, tracking, therapy, analysis"], BK),
        P("repositories", ["identity, clinical"], BK), P("schemas", ["common, accounts, tracking, device"], BK),
        P("ai", ["base, features, registry,", "rules_baseline"], BK), P("db", ["models, session"], BK),
        P("core", ["config, errors, security,", "ratelimit, logging, pagination"], BK), P("alembic", ["migraciones 0001-0003"], BK),
        P("infra/aws", ["CDK: stacks, servicio, CloudFront"], BK),
        P("App / main", ["arranque y rutas"], WB), P("pages", ["public, patient,", "professional, admin"], WB),
        P("components", ["ui, therapy, signature,", "Layout, Clinical"], WB), P("auth", ["AuthContext, RequireRole"], WB),
        P("hooks", ["useApi, usePaged"], WB), P("api", ["client, endpoints,", "adapters, types"], WB),
        P("i18n", ["es.json"], WB), P("mocks", ["MSW (desarrollo)"], WB), P("proxy (api/proxy.mjs)", ["función de Vercel"], WB),
        P("Control", ["SessionManager, LevelManager,", "GameStateManager, XRBootstrap"], VR),
        P("Comunicacion", ["FastAPIClient, RecordOutbox,", "DeviceRecordMapper"], VR),
        P("Metricas", ["MetricsCollector, SessionReport"], VR), P("Entidades", ["AranaController, IPhobiaStimulus"], VR),
        P("UI", ["GlobalSessionUI, BreathingGuide"], VR), P("Menu", ["NeuroPhobiaMenuBridge"], VR),
        P("Nivel2..Nivel5", ["scripts por nivel"], VR), P("Ajustes por nivel", ["carpetas NeuroPhobia_*"], VR),
        P("Scenes", ["MainMenu, Nivel1..Nivel5"], VR), P("Editor", ["BuildQuest3, tests de contrato"], VR),
        P("UnityEngine / XR Toolkit / OpenXR", ["paquetes externos"], VR, "library"),
    ]
    b = boxes(*items)
    rows = [[g] + [i.name for i in items if i.group == g] for g in (BK, WB, VR)]
    D = lambda a, c, l="«import»": Edge(a, c, "dep", l)  # noqa: E731
    edges = [
        D("main / cli", "api.routes"), D("main / cli", "services"), D("api.routes", "services"), D("api.routes", "api.deps"),
        D("api.routes", "schemas"), D("api.deps", "services"), D("api.deps", "repositories"), D("services", "repositories"),
        D("services", "schemas"), D("services", "ai"), D("services", "core"), D("repositories", "db"), D("db", "core"),
        D("core", "db", "«import» (diferido)"), D("alembic", "db"),
        D("App / main", "pages"), D("App / main", "auth"), D("pages", "components"), D("pages", "hooks"), D("pages", "api"),
        D("pages", "i18n"), D("components", "api"), D("components", "hooks"), D("auth", "api"), D("hooks", "api"), D("mocks", "api"),
        D("Control", "Comunicacion"), D("Control", "Metricas"), D("Control", "Entidades"), D("Comunicacion", "Metricas"),
        D("Metricas", "Control"), D("Metricas", "Entidades"), D("UI", "Control"), D("UI", "Comunicacion"), D("Menu", "Control"),
        D("Nivel2..Nivel5", "Control"), D("Nivel2..Nivel5", "Metricas"), D("Nivel2..Nivel5", "Entidades"),
        D("Ajustes por nivel", "Control"), D("Ajustes por nivel", "Metricas"), D("Ajustes por nivel", "UI"),
        D("Scenes", "Ajustes por nivel", "«use»"), D("Editor", "Comunicacion"),
        D("Control", "UnityEngine / XR Toolkit / OpenXR"),
        D("api", "api.routes", "«use» HTTP /api/v1"), D("Comunicacion", "api.routes", "«use» HTTP /api/v1/device"),
        D("proxy (api/proxy.mjs)", "api.routes", "«use» reenvía"),
    ]
    return Diagram("05_paquetes", "NEUROPHOBIA - Diagrama de paquetes", rows, b, edges,
                   groups={BK: "repositorio", WB: "repositorio", VR: "repositorio Assets"}, puml_kind="package")


if __name__ == "__main__":
    for d in (er(), clases_backend_entidades(), clases_backend_logica(), clases_unity(), componentes_sistema(),
              componentes_internos(), paquetes()):
        render_drawio(d)
        render_puml(d)
        print("ok", d.file)
