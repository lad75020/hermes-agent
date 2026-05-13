"""OpenAI request cancellation preserves caller scope and interrupts active work."""

import asyncio
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from aiohttp.test_utils import TestClient, TestServer

from tests.gateway.test_api_server import _create_app, adapter as adapter


class TestAPIRequestCancellation:
    @pytest.mark.asyncio
    async def test_cancel_request_interrupts_active_agent_and_task(self, adapter):
        request_id = "req-test-cancel"
        mock_agent = MagicMock()
        mock_task = MagicMock()
        mock_task.done.return_value = False
        mock_task.cancel = MagicMock()
        scope = adapter._run_idempotency_scope(SimpleNamespace(headers={}))
        adapter._active_api_agent_refs[(scope, request_id)] = [mock_agent]
        adapter._active_api_tasks[(scope, request_id)] = mock_task

        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(f"/v1/requests/{request_id}/cancel")
            assert resp.status == 200
            data = await resp.json()

        assert data == {"request_id": request_id, "status": "cancelling"}
        mock_agent.interrupt.assert_called_once_with("Cancel requested via API")
        mock_task.cancel.assert_called_once_with()

    @pytest.mark.asyncio
    async def test_cancel_request_returns_404_for_unknown_request(self, adapter):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post("/v1/requests/not-running/cancel")
            assert resp.status == 404
            data = await resp.json()

        assert data["error"]["code"] == "request_not_found"


    @pytest.mark.asyncio
    async def test_cancel_cannot_interrupt_another_profile_request(self, adapter):
        request_id = "shared-request-id"
        agent = MagicMock()
        task = MagicMock()
        adapter._active_api_agent_refs[("other-profile", request_id)] = [agent]
        adapter._active_api_tasks[("other-profile", request_id)] = task
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(f"/v1/requests/{request_id}/cancel")
            assert resp.status == 404
        agent.interrupt.assert_not_called()
        task.cancel.assert_not_called()

    @pytest.mark.asyncio
    async def test_completed_request_tracking_is_removed(self, adapter):
        scope = "test-owner"
        task = asyncio.get_running_loop().create_future()
        adapter._track_api_request("req-cleanup", [None], task, scope=scope)
        finished = asyncio.Event()
        task.add_done_callback(lambda _: finished.set())
        task.set_result(None)
        await finished.wait()
        assert (scope, "req-cleanup") not in adapter._active_api_tasks
        assert (scope, "req-cleanup") not in adapter._active_api_agent_refs

    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,body", [
        ("/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]}),
        ("/v1/responses", {"input": "hi"}),
    ])
    async def test_invalid_request_id_is_rejected(self, adapter, path, body):
        app = _create_app(adapter)
        async with TestClient(TestServer(app)) as cli:
            resp = await cli.post(path, json=body, headers={"X-Hermes-Request-Id": "bad id"})
            assert resp.status == 400
            assert (await resp.json())["error"]["code"] == "invalid_request_id"


    @pytest.mark.asyncio
    @pytest.mark.parametrize("path,body", [
        ("/v1/chat/completions", {"messages": [{"role": "user", "content": "hi"}]}),
        ("/v1/responses", {"input": "hi"}),
    ])
    async def test_cancel_interrupts_a_nonstreaming_request(self, adapter, path, body):
        started = asyncio.Event()
        pending = asyncio.Event()
        agent = MagicMock()

        async def run_agent(**kwargs):
            kwargs["agent_ref"][0] = agent
            started.set()
            await pending.wait()

        app = _create_app(adapter)
        with patch.object(adapter, "_run_agent", side_effect=run_agent):
            async with TestClient(TestServer(app)) as cli:
                completion = asyncio.create_task(cli.post(
                    path, json=body, headers={"X-Hermes-Request-Id": "req-live"}))
                try:
                    await asyncio.wait_for(started.wait(), timeout=5)
                    cancel = await cli.post("/v1/requests/req-live/cancel")
                    assert cancel.status == 200
                    response = await completion
                    assert response.status == 499
                    assert (await response.json())["error"]["code"] == "request_cancelled"
                finally:
                    completion.cancel()
        agent.interrupt.assert_called_once_with("Cancel requested via API")
