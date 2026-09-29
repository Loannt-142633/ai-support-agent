"""HTTP models for the internal staff demo agent."""

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class AgentAskRequest(BaseModel):
    """Only a staff message is accepted from the client."""

    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1)

    @field_validator("message")
    @classmethod
    def strip_nonempty_message(cls, value: str) -> str:
        message = value.strip()
        if not message:
            raise ValueError("message must not be blank")
        return message


class AgentAskResponse(BaseModel):
    """Answer for staff inspection; never a draft or outgoing email."""

    ticket_id: UUID
    answer: str
