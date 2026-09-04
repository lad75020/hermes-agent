import json
from types import SimpleNamespace

import httpx
import pytest


@pytest.mark.asyncio
async def test_mcpo_openapi_discovers_and_calls_xcode_tool():
    from tools.openapi_tool import OpenAPIServerTask

    spec = {
        "openapi": "3.1.0",
        "info": {"title": "xcode-tools", "version": "1"},
        "paths": {
            "/XcodeListWindows": {
                "post": {
                    "operationId": "tool_XcodeListWindows_post",
                    "description": "Lists the workspaces currently open in Xcode.",
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=spec)
        if request.url.path == "/XcodeListWindows":
            return httpx.Response(200, json="No workspaces are currently open.")
        return httpx.Response(404)

    server = OpenAPIServerTask(
        "XCodeMCP",
        transport=httpx.MockTransport(handler),
    )
    await server.start(
        {
            "transport": "openapi",
            "url": "http://127.0.0.1:8084",
            "openapi_url": "http://127.0.0.1:8084/openapi.json",
        }
    )

    assert [(tool.name, tool.inputSchema) for tool in server._tools] == [
        (
            "XcodeListWindows",
            {"type": "object", "properties": {}, "additionalProperties": False},
        )
    ]

    result = await server.session.call_tool("XcodeListWindows", arguments={})
    assert result.isError is False
    assert result.content[0].text == "No workspaces are currently open."
    assert requests[-1].method == "POST"
    assert requests[-1].url.path == "/XcodeListWindows"

    await server.shutdown()


@pytest.mark.asyncio
async def test_openapi_maps_path_query_headers_and_json_body():
    from tools.openapi_tool import OpenAPIServerTask

    spec = {
        "openapi": "3.0.3",
        "info": {"title": "example", "version": "1"},
        "paths": {
            "/projects/{project_id}": {
                "post": {
                    "operationId": "updateProject",
                    "parameters": [
                        {
                            "name": "project_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "verbose",
                            "in": "query",
                            "schema": {"type": "boolean"},
                        },
                        {
                            "name": "X-Trace-Id",
                            "in": "header",
                            "schema": {"type": "string"},
                        },
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/ProjectUpdate"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
        "components": {
            "schemas": {
                "ProjectUpdate": {
                    "type": "object",
                    "properties": {"name": {"type": "string"}},
                    "required": ["name"],
                }
            }
        },
    }
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=spec)
        observed.update(
            method=request.method,
            path=request.url.path,
            raw_path=request.url.raw_path.decode(),
            query=dict(request.url.params),
            headers=dict(request.headers),
            json=json.loads(request.content),
        )
        return httpx.Response(200, json={"updated": True})

    server = OpenAPIServerTask("example", transport=httpx.MockTransport(handler))
    await server.start(
        {
            "transport": "openapi",
            "url": "https://api.example.test/v1/",
            "openapi_url": "https://api.example.test/openapi.json",
            "headers": {"X-Static": "configured"},
        }
    )

    tool = server._tools[0]
    assert tool.name == "updateProject"
    assert tool.inputSchema["required"] == ["project_id", "name"]
    assert set(tool.inputSchema["properties"]) == {
        "project_id",
        "verbose",
        "X-Trace-Id",
        "name",
    }

    result = await server.session.call_tool(
        "updateProject",
        arguments={
            "project_id": "alpha beta",
            "verbose": True,
            "X-Trace-Id": "trace-1",
            "name": "Hermes",
        },
    )

    assert result.isError is False
    assert observed["method"] == "POST"
    assert observed["path"] == "/v1/projects/alpha beta"
    assert observed["raw_path"] == "/v1/projects/alpha%20beta?verbose=true"
    assert observed["query"] == {"verbose": "true"}
    assert observed["json"] == {"name": "Hermes"}
    assert observed["headers"]["x-static"] == "configured"
    assert observed["headers"]["x-trace-id"] == "trace-1"

    await server.shutdown()


@pytest.mark.asyncio
async def test_connect_server_routes_explicit_openapi_transport(monkeypatch):
    from tools import mcp_tool_discovery

    started = []

    class FakeOpenAPIServerTask:
        def __init__(self, name):
            self.name = name

        async def start(self, config):
            started.append(config)

    monkeypatch.setattr(
        "tools.openapi_tool.OpenAPIServerTask",
        FakeOpenAPIServerTask,
    )

    server = await mcp_tool_discovery._connect_server(
        "XCodeMCP",
        {"transport": "openapi", "url": "http://127.0.0.1:8084"},
    )

    assert server.name == "XCodeMCP"
    assert started == [
        {"transport": "openapi", "url": "http://127.0.0.1:8084"}
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "file:///tmp/openapi"),
        ("openapi_url", "https:///openapi.json"),
    ],
)
async def test_openapi_rejects_non_http_or_hostless_urls(field, value):
    from tools.openapi_tool import OpenAPIServerTask

    config = {
        "transport": "openapi",
        "url": "https://api.example.test",
        "openapi_url": "https://api.example.test/openapi.json",
    }
    config[field] = value

    server = OpenAPIServerTask("example")
    with pytest.raises(ValueError, match=field):
        await server.start(config)


def test_openapi_server_is_compatible_with_mcp_status(monkeypatch):
    from tools import mcp_tool_discovery
    from tools.openapi_tool import OpenAPIServerTask

    server = OpenAPIServerTask("XCodeMCP")
    server.session = SimpleNamespace()
    server._registered_tool_names = ["mcp__XCodeMCP__XcodeListWorkspaces"]
    monkeypatch.setattr(
        mcp_tool_discovery._config,
        "_load_mcp_config",
        lambda: {
            "XCodeMCP": {
                "transport": "openapi",
                "url": "http://127.0.0.1:8084",
            }
        },
    )
    monkeypatch.setitem(mcp_tool_discovery._core._servers, "XCodeMCP", server)

    assert mcp_tool_discovery.get_mcp_status() == [
        {
            "name": "XCodeMCP",
            "transport": "openapi",
            "tools": 1,
            "connected": True,
            "disabled": False,
            "status": "connected",
        }
    ]


def test_optional_and_colliding_json_bodies_use_nested_body_arguments():
    from tools.openapi_tool import parse_openapi_operations

    body_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "name": {"type": "string"},
        },
        "required": ["name"],
    }
    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/optional": {
                "patch": {
                    "operationId": "optionalBody",
                    "requestBody": {
                        "required": False,
                        "content": {"application/json": {"schema": body_schema}},
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
            "/items/{id}": {
                "patch": {
                    "operationId": "collidingBody",
                    "parameters": [
                        {
                            "name": "id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "requestBody": {
                        "required": True,
                        "content": {"application/json": {"schema": body_schema}},
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            },
        },
    }

    optional, colliding = parse_openapi_operations(spec)
    assert optional.input_schema["properties"]["body"] == body_schema
    assert "required" not in optional.input_schema
    assert optional.body_argument == "body"
    assert colliding.input_schema["required"] == ["id", "body"]
    assert colliding.input_schema["properties"]["body"] == body_schema
    assert colliding.body_argument == "body"


def test_operations_with_unsupported_request_body_media_are_not_exposed():
    from tools.openapi_tool import parse_openapi_operations

    spec = {
        "openapi": "3.0.3",
        "paths": {
            "/upload": {
                "post": {
                    "operationId": "uploadFile",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "multipart/form-data": {
                                "schema": {"type": "object"}
                            }
                        },
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    assert parse_openapi_operations(spec) == []


@pytest.mark.asyncio
async def test_openapi_honors_standard_parameter_serialization():
    from tools.openapi_tool import OpenAPIServerTask

    spec = {
        "openapi": "3.1.0",
        "paths": {
            "/search/{coords}": {
                "get": {
                    "operationId": "search",
                    "parameters": [
                        {
                            "name": "coords",
                            "in": "path",
                            "required": True,
                            "style": "simple",
                            "schema": {"type": "array", "items": {"type": "integer"}},
                        },
                        {
                            "name": "filter",
                            "in": "query",
                            "style": "deepObject",
                            "explode": True,
                            "schema": {"type": "object"},
                        },
                        {
                            "name": "tags",
                            "in": "query",
                            "style": "pipeDelimited",
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                        {
                            "name": "target",
                            "in": "query",
                            "allowReserved": True,
                            "schema": {"type": "string"},
                        },
                        {
                            "name": "X-Options",
                            "in": "header",
                            "style": "simple",
                            "explode": True,
                            "schema": {"type": "object"},
                        },
                        {
                            "name": "session",
                            "in": "cookie",
                            "style": "form",
                            "explode": True,
                            "schema": {"type": "array", "items": {"type": "string"}},
                        },
                    ],
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }
    observed = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/openapi.json":
            return httpx.Response(200, json=spec)
        observed["raw_path"] = request.url.raw_path.decode()
        observed["headers"] = dict(request.headers)
        observed["content"] = request.content
        return httpx.Response(200, json={"ok": True})

    server = OpenAPIServerTask("serialization", transport=httpx.MockTransport(handler))
    await server.start(
        {"transport": "openapi", "url": "https://api.example.test"}
    )
    result = await server.session.call_tool(
        "search",
        {
            "coords": [1, 2],
            "filter": {"role": "admin"},
            "tags": ["swift", "xcode"],
            "target": "docs/path?section=api",
            "X-Options": {"active": True, "role": "admin"},
            "session": ["a", "b"],
        },
    )

    assert result.isError is False
    assert observed["raw_path"] == (
        "/search/1,2?filter[role]=admin&tags=swift%7Cxcode&"
        "target=docs/path?section=api"
    )
    assert observed["headers"]["x-options"] == "active=true,role=admin"
    assert observed["headers"]["cookie"] == "session=a; session=b"
    assert observed["content"] == b""
    await server.shutdown()
