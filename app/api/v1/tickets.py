"""Ticket HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import get_ticket_service
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.schemas.ticket import TicketCreate, TicketListResponse, TicketResponse, TicketUpdate
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])
TicketServiceDependency = Annotated[TicketService, Depends(get_ticket_service)]


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(
    payload: TicketCreate, service: TicketServiceDependency
) -> TicketResponse:
    try:
        ticket = await service.create(**payload.model_dump())
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.get("", response_model=TicketListResponse)
async def list_tickets(
    service: TicketServiceDependency,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
    status_filter: Annotated[TicketStatus | None, Query(alias="status")] = None,
    category: Annotated[TicketCategory | None, Query()] = None,
    priority: Annotated[TicketPriority | None, Query()] = None,
    user_id: Annotated[UUID | None, Query()] = None,
) -> TicketListResponse:
    tickets, total = await service.list(
        page=page,
        page_size=page_size,
        status=status_filter,
        category=category,
        priority=priority,
        user_id=user_id,
    )
    return TicketListResponse(
        items=[TicketResponse.model_validate(ticket, from_attributes=True) for ticket in tickets],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.get("/{ticket_id}", response_model=TicketResponse)
async def get_ticket(ticket_id: UUID, service: TicketServiceDependency) -> TicketResponse:
    try:
        ticket = await service.get(ticket_id)
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.patch("/{ticket_id}", response_model=TicketResponse)
async def update_ticket(
    ticket_id: UUID, payload: TicketUpdate, service: TicketServiceDependency
) -> TicketResponse:
    try:
        ticket = await service.update(ticket_id, **payload.model_dump(exclude_unset=True))
        return TicketResponse.model_validate(ticket, from_attributes=True)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error


@router.delete("/{ticket_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_ticket(ticket_id: UUID, service: TicketServiceDependency) -> Response:
    try:
        await service.delete(ticket_id)
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    except LookupError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
