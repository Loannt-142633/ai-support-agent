"""User application service."""

from uuid import UUID

from app.models.user import User
from app.repositories.user_repository import UserRepository


class UserService:
    """Coordinate user workflows and repository transactions."""

    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def create(self, name: str, email: str) -> User:
        if self._repository.exists_by_email(email):
            raise ValueError("A user with this email already exists")
        return self._repository.create(name, email)

    def get(self, user_id: UUID) -> User:
        user = self._repository.get(user_id)
        if user is None:
            raise LookupError("User not found")
        return user

    def list(self) -> list[User]:
        return self._repository.list()

    def update(self, user_id: UUID, **changes: str) -> User:
        user = self.get(user_id)
        email = changes.get("email")
        if email is not None and self._repository.exists_by_email(email, excluding=user_id):
            raise ValueError("A user with this email already exists")
        return self._repository.update(user, **changes)

    def delete(self, user_id: UUID) -> None:
        self._repository.delete(self.get(user_id))
