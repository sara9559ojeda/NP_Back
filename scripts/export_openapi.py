"""Exporta el OpenAPI generado por FastAPI a ``docs/api/openapi.json``.

Uso: ``python scripts/export_openapi.py`` (o ``--check`` para fallar si el archivo no está al día).
No se conecta a la base de datos: si faltan las variables, usa valores efímeros de relleno.
"""

import json
import os
import secrets
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "api" / "openapi.json"


def render() -> str:
    os.environ.setdefault("NP_DATABASE_URL", "postgresql+psycopg://sin-conexion@localhost:1/none")
    os.environ.setdefault("NP_SECRET_KEY", secrets.token_urlsafe(48))
    sys.path.insert(0, str(ROOT))
    from app.main import create_app

    return json.dumps(create_app().openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    content = render()
    if "--check" in sys.argv:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != content:
            print("docs/api/openapi.json no está al día: ejecuta python scripts/export_openapi.py")
            return 1
        return 0
    TARGET.write_text(content, encoding="utf-8", newline="\n")
    print(f"Escrito {TARGET.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
