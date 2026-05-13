"""Cancellation of OpenAI requests, scoped like the API's idempotency cache."""

import asyncio
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class APIRequestCancellationMixin:
    @staticmethod
    def _normalize_api_request_id(value: Any) -> str:
        request_id = str(value or "").strip()
        if not request_id or len(request_id) > 128:
            return ""
        return request_id if re.fullmatch(r"[A-Za-z0-9_.:-]+", request_id) else ""

    def _api_request_id(self, request):
        from aiohttp import web
        from gateway.platforms.api_server import _openai_error
        raw = request.headers.get("X-Hermes-Request-Id", "")
        request_id = self._normalize_api_request_id(raw)
        if raw and not request_id:
            return "", web.json_response(
                _openai_error("Invalid X-Hermes-Request-Id", code="invalid_request_id"), status=400)
        return request_id, None

    def _track_api_request(self, request_id, agent_ref, task, *, scope):
        request_id = self._normalize_api_request_id(request_id)
        if not request_id:
            return
        key = (scope, request_id)
        self._active_api_agent_refs[key] = agent_ref
        self._active_api_tasks[key] = task

        def _cleanup(done_task):
            if self._active_api_tasks.get(key) is done_task:
                self._active_api_tasks.pop(key, None)
                self._active_api_agent_refs.pop(key, None)

        task.add_done_callback(_cleanup)

    async def _run_cancellable_agent(self, request, request_id, **run_kwargs):
        if not request_id:
            return await self._run_agent(**run_kwargs)
        agent_ref = [None]
        task = asyncio.create_task(self._run_agent(agent_ref=agent_ref, **run_kwargs))
        self._track_api_request(request_id, agent_ref, task, scope=self._run_idempotency_scope(request))
        return await task

    async def _handle_cancel_request(self, request):
        """Interrupt the request belonging to this authenticated profile and API key."""
        from aiohttp import web
        from gateway.platforms.api_server import _openai_error
        auth_err = self._check_auth(request)
        if auth_err is not None:
            return auth_err
        request_id = self._normalize_api_request_id(request.match_info.get("request_id", ""))
        if not request_id:
            return web.json_response(_openai_error("Invalid request id", code="invalid_request_id"), status=400)
        key = (self._run_idempotency_scope(request), request_id)
        agent_ref = self._active_api_agent_refs.get(key)
        task = self._active_api_tasks.get(key)
        if agent_ref is None and task is None:
            return web.json_response(
                _openai_error(f"Request not found: {request_id}", code="request_not_found"), status=404)
        agent = agent_ref[0] if agent_ref else None
        if agent is not None:
            try:
                agent.interrupt("Cancel requested via API")
            except Exception:
                logger.debug("API cancellation interrupt failed", exc_info=True)
        if task is not None and not task.done():
            task.cancel()
        return web.json_response({"request_id": request_id, "status": "cancelling"})
