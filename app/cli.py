"""Órdenes de administración local.

``python -m app.cli create-admin`` crea el primer administrador. Pide el nombre, el correo y la
contraseña por la terminal (la contraseña no se muestra), así no quedan en ningún archivo ni en
el historial de órdenes. En Docker: ``docker compose exec api python -m app.cli create-admin``.
"""

import argparse
import getpass
import sys

from pydantic import TypeAdapter, ValidationError

from app.core.errors import ApiError
from app.db.session import _session_factory
from app.schemas.accounts import PASSWORD_MAX, PASSWORD_MIN, Email
from app.services.auth import create_account


def create_admin() -> int:
    full_name = input("Nombre completo: ").strip()
    try:
        email = TypeAdapter(Email).validate_python(input("Correo: "))
    except ValidationError:
        print("Correo no válido.")
        return 1
    password = getpass.getpass("Contraseña: ")
    if not PASSWORD_MIN <= len(password) <= PASSWORD_MAX or password != getpass.getpass("Repite la contraseña: "):
        print(f"La contraseña debe tener entre {PASSWORD_MIN} y {PASSWORD_MAX} caracteres y coincidir.")
        return 1
    if not full_name:
        print("Falta el nombre.")
        return 1
    db = _session_factory()()
    try:
        create_account(db, email=email, password=password, role="admin", full_name=full_name)
        db.commit()
    except ApiError as exc:
        print(f"No se pudo crear: {exc.code}")
        return 1
    finally:
        db.close()
    print("Administrador creado.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.cli")
    parser.add_argument("command", choices=["create-admin"])
    args = parser.parse_args(argv)
    if args.command == "create-admin":
        return create_admin()
    return 1


if __name__ == "__main__":
    sys.exit(main())
