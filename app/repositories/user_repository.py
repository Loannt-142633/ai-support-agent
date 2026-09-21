"""SQLAlchemy repository for users."""

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    """Persist and query users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str, email: str) -> User:
        user = User(name=name, email=email)
        self._session.add(user)
        await self._session.flush()
        return user

    async def get(self, user_id: UUID) -> User | None:
        return await self._session.get(User, user_id)

    async def list(self, *, offset: int, limit: int) -> tuple[list[User], int]:
        query = select(User).order_by(User.created_at.desc()).offset(offset).limit(limit)
        result = await self._session.scalars(query)
        total = await self._session.scalar(select(func.count()).select_from(User))
        return list(result), total or 0

    async def update(self, user: User, **changes: str) -> User:
        for field, value in changes.items():
            setattr(user, field, value)
        await self._session.flush()
        return user

    async def delete(self, user: User) -> None:
        await self._session.delete(user)
        await self._session.flush()
