"""Rutas de administración (contrato, sección 4.4). El administrador no ve datos clínicos (D21)."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import JSONResponse

from app.api.deps import AdminUser, Db
from app.api.docs import problems
from app.core.pagination import Page, page_params
from app.schemas.accounts import (
    AdminPasswordReset,
    AdminUserCreate,
    AdminUserOut,
    AdminUserPage,
    AdminUserPatch,
    AssignmentCreate,
    AssignmentOut,
    AssignmentPage,
    Role,
)
from app.services import admin

router = APIRouter(prefix="/admin", tags=["admin"])

Pagination = Annotated[Page, Depends(page_params)]
NO_STORE = {"Cache-Control": "no-store"}


@router.get("/users", response_model=AdminUserPage, responses=problems(401, 403, 422, 423), summary="Usuarios (paginado)")
def list_users(
    actor: AdminUser,
    db: Db,
    page: Pagination,
    role: Role | None = None,
    active: bool | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
) -> AdminUserPage:
    return admin.list_users(db, page, role=role, active=active, q=q.strip() if q else None)


@router.post(
    "/users",
    status_code=status.HTTP_201_CREATED,
    response_model=AdminUserOut,
    responses=problems(401, 403, 409, 422, 423),
    summary="Crear un usuario con contraseña temporal",
)
def create_user(data: AdminUserCreate, actor: AdminUser, db: Db) -> AdminUserOut:
    return admin.create_user(db, data)


@router.get(
    "/users/{userId}",
    response_model=AdminUserOut,
    responses=problems(401, 403, 404, 423),
    summary="Perfil de un usuario (sin datos clínicos)",
)
def get_user(userId: uuid.UUID, actor: AdminUser, db: Db) -> AdminUserOut:  # noqa: N803
    return admin.get_user(db, userId)


@router.patch(
    "/users/{userId}",
    response_model=AdminUserOut,
    responses=problems(401, 403, 404, 409, 422, 423),
    summary="Editar el perfil: rol, activo, nombre o correo",
)
def patch_user(userId: uuid.UUID, data: AdminUserPatch, actor: AdminUser, db: Db) -> AdminUserOut:  # noqa: N803
    return admin.patch_user(db, userId, data)


@router.put(
    "/users/{userId}/password",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 403, 404, 422, 423),
    summary="Poner una contraseña temporal (cierra las sesiones web de ese usuario)",
)
def reset_password(userId: uuid.UUID, data: AdminPasswordReset, actor: AdminUser, db: Db) -> Response:  # noqa: N803
    admin.reset_password(db, userId, data.temporary_password)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/assignments",
    response_model=AssignmentPage,
    responses=problems(401, 403, 422, 423),
    summary="Asignaciones profesional–paciente activas",
)
def list_assignments(
    actor: AdminUser,
    db: Db,
    page: Pagination,
    professionalId: uuid.UUID | None = None,  # noqa: N803
) -> AssignmentPage:
    return admin.list_assignments(db, page, professionalId)


@router.post(
    "/assignments",
    status_code=status.HTTP_201_CREATED,
    response_model=AssignmentOut,
    responses={200: {"model": AssignmentOut, "description": "La asignación ya existía"}, **problems(401, 403, 422, 423)},
    summary="Asignar un paciente a un profesional",
)
def create_assignment(data: AssignmentCreate, actor: AdminUser, db: Db, response: Response) -> AssignmentOut:
    assignment, created = admin.create_assignment(db, data.professional_id, data.patient_id)
    if not created:
        response.status_code = status.HTTP_200_OK
    return assignment


@router.delete(
    "/assignments/{assignmentId}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses=problems(401, 403, 404, 423),
    summary="Quitar una asignación",
)
def delete_assignment(assignmentId: uuid.UUID, actor: AdminUser, db: Db) -> Response:  # noqa: N803
    admin.delete_assignment(db, assignmentId)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/exports/analysis-dataset",
    responses={
        200: {
            "description": "Conjunto anónimo (JSON por defecto; CSV con `Accept: text/csv`).",
            "content": {"application/json": {}, "text/csv": {}},
        },
        **problems(401, 403, 423),
    },
    summary="Exportación anónima para análisis (sin pseudonym_id, ids nuevos, sin sesiones de prueba)",
)
def export_dataset(actor: AdminUser, db: Db, request: Request) -> Response:
    dataset = admin.analysis_dataset(db)
    if "text/csv" in request.headers.get("accept", ""):
        return Response(
            admin.dataset_to_csv(dataset),
            media_type="text/csv; charset=utf-8",
            headers={**NO_STORE, "Content-Disposition": 'attachment; filename="neurophobia-analysis-dataset.csv"'},
        )
    return JSONResponse(dataset, headers=NO_STORE)
