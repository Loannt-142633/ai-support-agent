"""Local-only mock staff identity and explicit ticket allowlist."""

from dataclasses import dataclass
from ipaddress import ip_address
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request

from app.api.dependencies import get_gemini_staff_agent_model, get_ticket_repository
from app.core.config import Settings, get_settings
from app.repositories.fake_order_payments_repository import FakeOrderPaymentsRepository
from app.repositories.ticket_repository import TicketRepository
from app.services.agent_service import AgentService, StaffAgentModel
from app.services.order_payments_service import OrderPaymentsService
from app.tools.order_payments import (
    StaffToolDispatcher,
    ToolExecutionContext,
    load_tool_context,
)


@dataclass(frozen=True)
class DemoStaffIdentity:
    """Server-configured identity for local demonstrations only."""

    staff_id: str


class DemoStaffAuth:
    """Refuse requests unless local demo mode and a loopback peer are both present."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def authenticate(self, request: Request) -> DemoStaffIdentity:
        """Ignore client-claimed identities, roles and forwarded-for headers."""
        if not self._settings.demo_staff_auth_enabled or self._settings.app_env != "local":
            raise HTTPException(status_code=403, detail="Demo agent is disabled")
        peer = request.client.host if request.client is not None else ""
        try:
            if not ip_address(peer).is_loopback:
                raise HTTPException(status_code=403, detail="Demo agent requires loopback access")
        except ValueError as error:
            raise HTTPException(
                status_code=403, detail="Demo agent requires loopback access"
            ) from error
        return DemoStaffIdentity(staff_id=self._settings.demo_staff_id)


class DemoTicketAccess:
    """Only explicitly configured ticket IDs may enter the demo agent workflow."""

    def __init__(self, settings: Settings) -> None:
        self._allowed_ticket_ids = frozenset(settings.demo_staff_ticket_ids)

    def require(self, ticket_id: UUID, staff: DemoStaffIdentity) -> None:
        """Gate DB reads and model creation before loading ticket context."""
        if not staff.staff_id or ticket_id not in self._allowed_ticket_ids:
            raise HTTPException(status_code=403, detail="Ticket is not allowed for demo staff")


def get_demo_staff_auth() -> DemoStaffAuth:
    """Construct the local demo identity provider from backend settings."""
    return DemoStaffAuth(get_settings())


def get_demo_ticket_access() -> DemoTicketAccess:
    """Construct ticket access from backend settings, never request data."""
    return DemoTicketAccess(get_settings())


def get_demo_staff_identity(
    request: Request,
    auth: Annotated[DemoStaffAuth, Depends(get_demo_staff_auth)],
) -> DemoStaffIdentity:
    """Authenticate the peer before any ticket lookup."""
    return auth.authenticate(request)


def require_demo_ticket_access(
    ticket_id: UUID,
    staff: Annotated[DemoStaffIdentity, Depends(get_demo_staff_identity)],
    access: Annotated[DemoTicketAccess, Depends(get_demo_ticket_access)],
) -> None:
    """Authorize the path ticket ID before loading it from storage."""
    access.require(ticket_id, staff)


async def get_demo_tool_context(
    ticket_id: UUID,
    _access: Annotated[None, Depends(require_demo_ticket_access)],
    tickets: Annotated[TicketRepository, Depends(get_ticket_repository)],
) -> ToolExecutionContext:
    """Read one authorized ticket using the existing repository."""
    try:
        return await load_tool_context(ticket_id, tickets)
    except LookupError as error:
        raise HTTPException(status_code=404, detail="Ticket not found") from error


def get_demo_agent_service(
    _context: Annotated[ToolExecutionContext, Depends(get_demo_tool_context)],
    model: Annotated[StaffAgentModel, Depends(get_gemini_staff_agent_model)],
) -> AgentService[ToolExecutionContext]:
    """Create the internal agent only after demo access and ticket lookup pass."""
    return AgentService(
        model, StaffToolDispatcher(OrderPaymentsService(FakeOrderPaymentsRepository()))
    )
