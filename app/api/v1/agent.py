"""Guarded local demo endpoint for a staff agent question."""

import logging
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException

from app.api.demo_staff import get_demo_agent_service, get_demo_tool_context
from app.llm.exceptions import LLMError, LLMTimeoutError
from app.schemas.agent import AgentAskRequest, AgentAskResponse
from app.services.agent_service import AgentInvalidResponseError, AgentService
from app.tools.order_payments import ToolExecutionContext

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/tickets", tags=["agent"])


@router.post("/{ticket_id}/agent/ask", response_model=AgentAskResponse)
async def ask_demo_agent(
    ticket_id: UUID,
    payload: AgentAskRequest,
    context: Annotated[ToolExecutionContext, Depends(get_demo_tool_context)],
    agent: Annotated[
        AgentService[ToolExecutionContext], Depends(get_demo_agent_service)
    ],
) -> AgentAskResponse:
    """Return one answer after the demo auth and ticket allowlist gates."""
    try:
        answer = await agent.answer(payload.message, context=context)
    except LLMTimeoutError as error:
        logger.warning("Demo agent model timed out for ticket %s", ticket_id)
        raise HTTPException(status_code=504, detail="Agent timed out") from error
    except (LLMError, AgentInvalidResponseError) as error:
        logger.exception("Demo agent model failed for ticket %s", ticket_id)
        raise HTTPException(status_code=502, detail="Agent is unavailable") from error
    except Exception as error:
        logger.exception("Demo agent failed for ticket %s", ticket_id)
        raise HTTPException(status_code=502, detail="Agent is unavailable") from error
    return AgentAskResponse(ticket_id=ticket_id, answer=answer)
