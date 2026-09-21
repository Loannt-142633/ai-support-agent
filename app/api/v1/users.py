"""User HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.repositories.user_repository import UserRepository
from app.schemas.user import UserCreate, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])
DbSession = Annotated[Session, Depends(get_db)]


def _service(session: Session) -> UserService:
    return UserService(UserRepository(session))


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def create_user(payload: UserCreate, session: DbSession) -> UserResponse:
    try:
        user = _service(session).create(payload.name, str(payload.email))
        session.commit()
        session.refresh(user)
        return UserResponse.model_validate(user, from_attributes=True)
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("", response_model=list[UserResponse])
def list_users(session: DbSession) -> list[UserResponse]:
    users = _service(session).list()
    return [UserResponse.model_validate(user, from_attributes=True) for user in users]


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: UUID, session: DbSession) -> UserResponse:
    try:
        user = _service(session).get(user_id)
        return UserResponse.model_validate(user, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{user_id}", response_model=UserResponse)
def update_user(user_id: UUID, payload: UserUpdate, session: DbSession) -> UserResponse:
    changes = payload.model_dump(exclude_unset=True)
    try:
        user = _service(session).update(user_id, **changes)
        session.commit()
        session.refresh(user)
        return UserResponse.model_validate(user, from_attributes=True)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        session.rollback()
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_user(user_id: UUID, session: DbSession) -> Response:
    try:
        _service(session).delete(user_id)
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
