"""SQLAlchemy repository for users."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.user import User


class UserRepository:
    """Persist and query users."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, name: str, email: str) -> User:
        user = User(name=name, email=email)
        self._session.add(user)
        self._session.flush()
        return user

    def get(self, user_id: UUID) -> User | None:
        return self._session.get(User, user_id)

    def list(self) -> list[User]:
        return list(self._session.scalars(select(User).order_by(User.created_at.desc())))

    def update(self, user: User, **changes: str) -> User:
        for field, value in changes.items():
            setattr(user, field, value)
        self._session.flush()
        return user

    def delete(self, user: User) -> None:
        self._session.delete(user)
        self._session.flush()

    def exists_by_email(self, email: str, excluding: UUID | None = None) -> bool:
        statement = select(User.id).where(User.email == email)
        if excluding is not None:
            statement = statement.where(User.id != excluding)
        return self._session.scalar(statement) is not None
