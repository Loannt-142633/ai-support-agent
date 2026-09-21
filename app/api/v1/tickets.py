"""Ticket HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.repositories.ticket_repository import TicketRepository
from app.repositories.user_repository import UserRepository
from app.schemas.ticket import TicketCreate, TicketResponse, TicketUpdate
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])
DbSession = Annotated[Session, Depends(get_db)]


def _service(session: Session) -> TicketService:
    return TicketService(TicketRepository(session), UserRepository(session))


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
def create_ticket(payload: TicketCreate, session: DbSession) -> TicketResponse:
    try:
        ticket = _service(session).create(**payload.model_dump())
        session.commit()
        session.refresh(ticket)
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("", response_model=list[TicketResponse])
def list_tickets(
    session: DbSession,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    category: Annotated[TicketCategory | None, Query()] = None,
    priority: Annotated[TicketPriority | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
) -> list[TicketResponse]:
    tickets = _service(session).list(
        status=status_filter, category=category, priority=priority, user_id=user_id
    )
    return [TicketResponse.model_validate(ticket, from_attributes=True) for ticket in tickets]


@router.get("/{ticket_id}", response_model=TicketResponse)
def get_ticket(ticket_id: UUID, session: DbSession) -> TicketResponse:
    try:
        ticket = _service(session).get(ticket_id)
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{ticket_id}", response_model=TicketResponse)
def update_ticket(ticket_id: UUID, payload: TicketUpdate, session: DbSession) -> TicketResponse:
    try:
        ticket = _service(session).update(ticket_id, **payload.model_dump(exclude_unset=True))
        session.commit()
        session.refresh(ticket)
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ticket(ticket_id: UUID, session: DbSession) -> Response:
    try:
        _service(session).delete(ticket_id)
        session.commit()
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LookupError as error:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(error)) from error
