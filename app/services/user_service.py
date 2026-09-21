"""User application service."""

from uuid import UUID

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    """Coordinate user workflows and repository transactions."""

    def __init__(self, repository: UserRepository, session: AsyncSession) -> None:
        self._repository = repository
        self._session = session

    async def create(self, name: str, email: str) -> User:
        try:
            user = await self._repository.create(name, email)
            await self._session.commit()
            await self._session.refresh(user)
            return user
        except IntegrityError as error:
            await self._session.rollback()
            raise ValueError("A user with this email already exists") from error

    async def get(self, user_id: UUID) -> User:
        user = await self._repository.get(user_id)
        if user is None:
            raise LookupError("User not found")
        return user

    async def list(self, *, page: int, page_size: int) -> tuple[list[User], int]:
        return await self._repository.list(
            offset=(page - 1) * page_size, limit=page_size
        )

    async def update(self, user_id: UUID, **changes: str) -> User:
        user = await self.get(user_id)
        try:
            user = await self._repository.update(user, **changes)
            await self._session.commit()
            await self._session.refresh(user)
            return user
        except IntegrityError as error:
            await self._session.rollback()
            raise ValueError("A user with this email already exists") from error

    async def delete(self, user_id: UUID) -> None:
        await self._repository.delete(await self.get(user_id))
        await self._session.commit()
