"""Ticket HTTP endpoints."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from app.api.dependencies import (
    get_suggested_answer_service,
    get_ticket_ai_analysis_repository,
    get_ticket_repository,
    get_ticket_service,
)
from app.models.ticket import TicketCategory, TicketPriority, TicketStatus
from app.repositories.ticket_ai_analysis_repository import TicketAIAnalysisRepository
from app.repositories.ticket_repository import TicketRepository
from app.schemas.ticket import (
    SuggestedAnswerResponse,
    TicketCreate,
    TicketListResponse,
    TicketResponse,
    TicketUpdate,
)
from app.schemas.ticket_ai_analysis import (
    TicketAnalysisCompletedResponse,
    TicketAnalysisPendingResponse,
)
from app.services.suggested_answer_service import SuggestedAnswerService
from app.services.ticket_service import TicketService

router = APIRouter(prefix="/tickets", tags=["tickets"])
TicketServiceDependency = Annotated[TicketService, Depends(get_ticket_service)]
TicketRepositoryDependency = Annotated[TicketRepository, Depends(get_ticket_repository)]
TicketAIAnalysisRepositoryDependency = Annotated[
    TicketAIAnalysisRepository, Depends(get_ticket_ai_analysis_repository)
]
SuggestedAnswerServiceDependency = Annotated[
    SuggestedAnswerService, Depends(get_suggested_answer_service)
]


@router.post("", response_model=TicketResponse, status_code=status.HTTP_201_CREATED)
async def create_ticket(payload: TicketCreate, service: TicketServiceDependency) -> TicketResponse:
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


@router.get(
    "/{ticket_id}/analysis",
    response_model=TicketAnalysisPendingResponse | TicketAnalysisCompletedResponse,
)
async def get_ticket_analysis(
    ticket_id: UUID,
    tickets: TicketRepositoryDependency,
    analyses: TicketAIAnalysisRepositoryDependency,
) -> TicketAnalysisPendingResponse | TicketAnalysisCompletedResponse:
    """Return the latest AI result, or pending while no result is available."""

    if await tickets.get(ticket_id) is None:
        raise HTTPException(status_code=404, detail="Ticket not found")

    analysis = await analyses.get_by_ticket_id(ticket_id)
    if analysis is None:
        return TicketAnalysisPendingResponse(ticket_id=ticket_id)
    return TicketAnalysisCompletedResponse(
        ticket_id=ticket_id,
        category=analysis.predicted_category,
        priority=analysis.predicted_priority,
        summary=analysis.summary,
        requires_human=analysis.requires_human,
    )


@router.post("/{ticket_id}/suggested-answer", response_model=SuggestedAnswerResponse)
async def create_suggested_answer(
    ticket_id: UUID,
    service: SuggestedAnswerServiceDependency,
) -> SuggestedAnswerResponse:
    """Generate a grounded draft for staff review without sending it."""

    try:
        answer = await service.generate(ticket_id)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Ticket not found") from error
    return SuggestedAnswerResponse(ticket_id=ticket_id, suggested_answer=answer)


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
