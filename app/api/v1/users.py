"""User HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_user_service
from app.schemas.user import UserCreate, UserListResponse, UserResponse, UserUpdate
from app.services.user_service import UserService

router = APIRouter(prefix="/users", tags=["users"])
UserServiceDependency = Annotated[UserService, Depends(get_user_service)]


@router.post("", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def create_user(payload: UserCreate, service: UserServiceDependency) -> UserResponse:
    try:
        user = await service.create(payload.name, str(payload.email))
        return UserResponse.model_validate(user, from_attributes=True)
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.get("", response_model=UserListResponse)
async def list_users(
    service: UserServiceDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
) -> UserListResponse:
    users, total = await service.list(page=page, page_size=page_size)
    return UserListResponse(
        items=[UserResponse.model_validate(user, from_attributes=True) for user in users],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, service: UserServiceDependency) -> UserResponse:
    try:
        user = await service.get(user_id)
        return UserResponse.model_validate(user, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: UUID, payload: UserUpdate, service: UserServiceDependency
) -> UserResponse:
    try:
        user = await service.update(user_id, **payload.model_dump(exclude_unset=True))
        return UserResponse.model_validate(user, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_user(user_id: UUID, service: UserServiceDependency) -> Response:
    try:
        await service.delete(user_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
