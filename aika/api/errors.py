"""Map store exceptions to the HTTP errors the API has always returned."""

from __future__ import annotations

from fastapi import HTTPException, status

from aika.agents.store import AgentTaskNotFoundError, InvalidAgentTaskError
from aika.conversation_store import ConversationNotFoundError, InvalidConversationError
from aika.eval.feedback import InvalidFeedbackError
from aika.eval.store import EvalRunNotFoundError, InvalidEvalRunError


def http_error_from_store(exc: Exception) -> HTTPException:
    if isinstance(exc, ConversationNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
    if isinstance(exc, InvalidConversationError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def http_error_from_agent_store(exc: Exception) -> HTTPException:
    if isinstance(exc, AgentTaskNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Agent task not found")
    if isinstance(exc, InvalidAgentTaskError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def http_error_from_eval_store(exc: Exception) -> HTTPException:
    if isinstance(exc, EvalRunNotFoundError):
        return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Eval run not found")
    if isinstance(exc, InvalidEvalRunError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


def http_error_from_feedback_store(exc: Exception) -> HTTPException:
    if isinstance(exc, InvalidFeedbackError):
        return HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
