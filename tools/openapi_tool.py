"""OpenAPI-backed external tool servers.

This module adapts a REST OpenAPI document to the small server/session surface
used by ``tools.mcp_tool``.  It deliberately requires an explicit
``transport: openapi`` configuration so an ordinary remote MCP URL is never
misinterpreted as REST.
"""

from __future__ import annotations

import asyncio
import copy
import json
import re
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Dict, Iterable, Optional
from urllib.parse import quote, urlparse

import httpx


_HTTP_METHODS = {"get", "put", "post", "delete", "options", "head", "patch", "trace"}
_MCPO_OPERATION_RE = re.compile(r"^tool_(?P<name>.+)_(?P<method>[a-z]+)$", re.IGNORECASE)


def is_openapi_server_config(config: dict) -> bool:
    """Return whether an external-server entry explicitly selects OpenAPI."""
    return str(config.get("transport", "")).strip().lower() == "openapi"


def _validate_http_url(server_name: str, field_name: str, value: Any) -> str:
    """Return a normalized absolute HTTP(S) URL for OpenAPI configuration."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError(
            f"OpenAPI server '{server_name}': {field_name} must be a non-empty URL"
        )
    normalized = value.strip()
    parsed = urlparse(normalized)
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError(
            f"OpenAPI server '{server_name}': {field_name} must use http or https "
            f"and include a hostname ({normalized!r})"
        )
    return normalized


def _json_pointer_get(document: dict, pointer: str) -> Any:
    if not pointer.startswith("#/"):
        raise ValueError(f"Only local OpenAPI references are supported: {pointer}")
    current: Any = document
    for raw_part in pointer[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if not isinstance(current, dict) or part not in current:
            raise ValueError(f"OpenAPI reference does not exist: {pointer}")
        current = current[part]
    return current


def _resolve_local_refs(value: Any, document: dict, stack: tuple[str, ...] = ()) -> Any:
    """Resolve local ``#/...`` references without mutating the source document."""
    if isinstance(value, list):
        return [_resolve_local_refs(item, document, stack) for item in value]
    if not isinstance(value, dict):
        return copy.deepcopy(value)

    reference = value.get("$ref")
    if isinstance(reference, str):
        if reference in stack:
            # Recursive JSON schemas are valid, but LLM tool schemas cannot
            # safely carry an infinitely expanded form. Keep the recursive ref.
            return copy.deepcopy(value)
        resolved = _resolve_local_refs(
            _json_pointer_get(document, reference), document, stack + (reference,)
        )
        if not isinstance(resolved, dict):
            return resolved
        merged = dict(resolved)
        merged.update(
            {
                key: _resolve_local_refs(item, document, stack)
                for key, item in value.items()
                if key != "$ref"
            }
        )
        return merged

    return {
        key: _resolve_local_refs(item, document, stack)
        for key, item in value.items()
    }


def _pick_json_schema(content: dict, document: dict) -> Optional[dict]:
    if not isinstance(content, dict):
        return None
    media = content.get("application/json")
    if media is None:
        media = next(
            (
                entry
                for mime, entry in content.items()
                if isinstance(mime, str) and mime.lower().endswith("+json")
            ),
            None,
        )
    if not isinstance(media, dict) or not isinstance(media.get("schema"), dict):
        return None
    return _resolve_local_refs(media["schema"], document)


def _operation_name(path: str, method: str, operation: dict) -> str:
    explicit = operation.get("x-hermes-tool-name")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()

    operation_id = operation.get("operationId")
    if isinstance(operation_id, str) and operation_id.strip():
        operation_id = operation_id.strip()
        match = _MCPO_OPERATION_RE.fullmatch(operation_id)
        if match and match.group("method").lower() == method:
            # mcpo generates operationIds such as
            # tool_XcodeListWindows_post. Preserve the original MCP tool name
            # so Hermes exposes mcp__XCodeMCP__XcodeListWindows.
            return match.group("name")
        return operation_id

    segment = path.rstrip("/").rsplit("/", 1)[-1] or "root"
    segment = re.sub(r"[{}]", "", segment)
    return f"{method}_{segment}"


def _parameter_schema(parameter: dict, document: dict) -> dict:
    schema = parameter.get("schema")
    if isinstance(schema, dict):
        return _resolve_local_refs(schema, document)
    content_schema = _pick_json_schema(parameter.get("content") or {}, document)
    return content_schema or {"type": "string"}


def _dedupe_required(names: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(name for name in names if isinstance(name, str)))


@dataclass(frozen=True)
class OpenAPIOperation:
    name: str
    method: str
    path: str
    description: str
    input_schema: dict
    parameters: tuple[dict, ...]
    body_schema: Optional[dict]
    body_argument: Optional[str]


def parse_openapi_operations(document: dict) -> list[OpenAPIOperation]:
    """Convert OpenAPI operations into Hermes/MCP-shaped tool descriptors."""
    if not isinstance(document, dict):
        raise ValueError("OpenAPI document must be a JSON object")
    version = str(document.get("openapi", ""))
    if not version.startswith("3."):
        raise ValueError(f"Unsupported OpenAPI version: {version or 'missing'}")

    operations: list[OpenAPIOperation] = []
    seen_names: set[str] = set()
    paths = document.get("paths")
    if not isinstance(paths, dict):
        raise ValueError("OpenAPI document has no paths object")

    for path, raw_path_item in paths.items():
        if not isinstance(path, str) or not isinstance(raw_path_item, dict):
            continue
        path_item = _resolve_local_refs(raw_path_item, document)
        inherited_parameters = path_item.get("parameters") or []
        for method, operation in path_item.items():
            method_lower = str(method).lower()
            if method_lower not in _HTTP_METHODS or not isinstance(operation, dict):
                continue

            name = _operation_name(path, method_lower, operation)
            if name in seen_names:
                raise ValueError(f"Duplicate OpenAPI tool name: {name}")
            seen_names.add(name)

            parameters = []
            parameter_names: set[str] = set()
            properties: Dict[str, Any] = {}
            required: list[str] = []
            for raw_parameter in [*inherited_parameters, *(operation.get("parameters") or [])]:
                parameter = _resolve_local_refs(raw_parameter, document)
                if not isinstance(parameter, dict):
                    continue
                parameter_name = parameter.get("name")
                location = parameter.get("in")
                if not isinstance(parameter_name, str) or location not in {
                    "path",
                    "query",
                    "header",
                    "cookie",
                }:
                    continue
                if parameter_name in parameter_names:
                    parameters = [p for p in parameters if p["name"] != parameter_name]
                parameter_names.add(parameter_name)
                parameters.append(parameter)
                properties[parameter_name] = _parameter_schema(parameter, document)
                if parameter.get("description") and "description" not in properties[parameter_name]:
                    properties[parameter_name]["description"] = parameter["description"]
                if parameter.get("required") is True or location == "path":
                    required.append(parameter_name)

            request_body = _resolve_local_refs(operation.get("requestBody") or {}, document)
            request_body_content = request_body.get("content") or {}
            body_schema = _pick_json_schema(request_body_content, document)
            if request_body_content and body_schema is None:
                # Hermes currently knows how to map JSON request bodies only.
                # Do not expose an operation that would silently drop a form,
                # multipart, text, or binary body at execution time.
                continue
            body_argument: Optional[str] = None
            if body_schema is not None:
                if body_schema.get("type") == "object" or isinstance(
                    body_schema.get("properties"), dict
                ):
                    body_properties = body_schema.get("properties") or {}
                    collisions = parameter_names.intersection(body_properties)
                    if request_body.get("required") is True and not collisions:
                        # Preserve mcpo's native MCP-like flat argument shape
                        # when it is unambiguous and the body is mandatory.
                        properties.update(copy.deepcopy(body_properties))
                        required.extend(body_schema.get("required") or [])
                    else:
                        # Optional bodies need a nested schema so their internal
                        # required fields stay conditional. Nesting also avoids
                        # collisions with path/query/header parameter names.
                        body_argument = "body"
                        while body_argument in parameter_names:
                            body_argument = "request_" + body_argument
                        properties[body_argument] = copy.deepcopy(body_schema)
                        if request_body.get("required") is True:
                            required.append(body_argument)
                else:
                    body_argument = "body"
                    while body_argument in parameter_names:
                        body_argument = "request_" + body_argument
                    properties[body_argument] = copy.deepcopy(body_schema)
                    if request_body.get("required") is True:
                        required.append(body_argument)

            input_schema = {
                "type": "object",
                "properties": properties,
                "additionalProperties": False,
            }
            required = _dedupe_required(required)
            if required:
                input_schema["required"] = required

            description = (
                operation.get("description")
                or operation.get("summary")
                or f"{method_lower.upper()} {path}"
            )
            operations.append(
                OpenAPIOperation(
                    name=name,
                    method=method_lower.upper(),
                    path=path,
                    description=str(description),
                    input_schema=input_schema,
                    parameters=tuple(parameters),
                    body_schema=body_schema,
                    body_argument=body_argument,
                )
            )

    return operations


def _encode_query_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def _explode_for(parameter: dict, style: str) -> bool:
    raw = parameter.get("explode")
    return style == "form" if raw is None else raw is True


def _simple_value(value: Any, *, explode: bool, encode=_encode_query_value) -> str:
    """Serialize OpenAPI ``simple`` values for paths and headers."""
    if isinstance(value, dict):
        if explode:
            return ",".join(
                f"{encode(key)}={encode(item)}" for key, item in value.items()
            )
        return ",".join(
            encoded
            for key, item in value.items()
            for encoded in (encode(key), encode(item))
        )
    if isinstance(value, (list, tuple)):
        return ",".join(encode(item) for item in value)
    return encode(value)


def _serialize_path_parameter(parameter: dict, value: Any) -> str:
    style = str(parameter.get("style") or "simple")
    explode = _explode_for(parameter, style)
    encode = lambda item: quote(str(item), safe="")
    if style == "simple":
        return _simple_value(value, explode=explode, encode=encode)
    if style == "label":
        if isinstance(value, dict) and explode:
            return "." + ".".join(
                f"{encode(key)}={encode(item)}" for key, item in value.items()
            )
        if isinstance(value, (list, tuple)) and explode:
            return "." + ".".join(encode(item) for item in value)
        return "." + _simple_value(value, explode=False, encode=encode)
    if style == "matrix":
        name = quote(str(parameter["name"]), safe="")
        if isinstance(value, dict) and explode:
            return "".join(
                f";{encode(key)}={encode(item)}" for key, item in value.items()
            )
        if isinstance(value, (list, tuple)) and explode:
            return "".join(f";{name}={encode(item)}" for item in value)
        return f";{name}=" + _simple_value(value, explode=False, encode=encode)
    raise ValueError(f"Unsupported OpenAPI path parameter style: {style}")


def _serialize_query_parameter(
    parameter: dict, value: Any
) -> list[tuple[str, str, bool]]:
    name = str(parameter["name"])
    style = str(parameter.get("style") or "form")
    explode = _explode_for(parameter, style)
    allow_reserved = parameter.get("allowReserved") is True

    if style == "deepObject":
        if not isinstance(value, dict):
            raise ValueError(f"OpenAPI deepObject parameter '{name}' requires an object")
        return [
            (f"{name}[{key}]", _encode_query_value(item), allow_reserved)
            for key, item in value.items()
        ]
    if style == "form":
        if isinstance(value, dict):
            if explode:
                return [
                    (str(key), _encode_query_value(item), allow_reserved)
                    for key, item in value.items()
                ]
            flattened = ",".join(
                part
                for key, item in value.items()
                for part in (str(key), _encode_query_value(item))
            )
            return [(name, flattened, allow_reserved)]
        if isinstance(value, (list, tuple)):
            if explode:
                return [
                    (name, _encode_query_value(item), allow_reserved) for item in value
                ]
            return [(name, ",".join(map(_encode_query_value, value)), allow_reserved)]
        return [(name, _encode_query_value(value), allow_reserved)]
    if style in {"spaceDelimited", "pipeDelimited"}:
        separator = " " if style == "spaceDelimited" else "|"
        values = value if isinstance(value, (list, tuple)) else [value]
        return [
            (name, separator.join(map(_encode_query_value, values)), allow_reserved)
        ]
    raise ValueError(f"Unsupported OpenAPI query parameter style: {style}")


def _serialize_cookie_parameter(parameter: dict, value: Any) -> list[tuple[str, str]]:
    name = str(parameter["name"])
    style = str(parameter.get("style") or "form")
    if style != "form":
        raise ValueError(f"Unsupported OpenAPI cookie parameter style: {style}")
    explode = _explode_for(parameter, style)
    if isinstance(value, dict):
        if explode:
            return [(str(key), _encode_query_value(item)) for key, item in value.items()]
        flattened = ",".join(
            part
            for key, item in value.items()
            for part in (str(key), _encode_query_value(item))
        )
        return [(name, flattened)]
    if isinstance(value, (list, tuple)):
        if explode:
            return [(name, _encode_query_value(item)) for item in value]
        return [(name, ",".join(map(_encode_query_value, value)))]
    return [(name, _encode_query_value(value))]


_RESERVED_QUERY_CHARACTERS = ":/?#[]@!$&'()*+,;="


def _apply_query(url: httpx.URL, query: list[tuple[str, str, bool]]) -> httpx.URL:
    if not query:
        return url
    encoded = "&".join(
        f"{quote(name, safe='[]')}="
        f"{quote(value, safe=_RESERVED_QUERY_CHARACTERS if allow_reserved else '')}"
        for name, value, allow_reserved in query
    )
    return url.copy_with(query=encoded.encode("ascii"))


def _text_result(text: str, *, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(type="text", text=text)],
        isError=is_error,
        is_error=is_error,
        structuredContent=None,
        structured_content=None,
        meta=None,
    )


class OpenAPISession:
    """Session adapter exposing the MCP ``call_tool`` method shape."""

    def __init__(self, server: "OpenAPIServerTask") -> None:
        self._server = server

    async def call_tool(self, tool_name: str, arguments: Optional[dict] = None):
        operation = self._server._operations.get(tool_name)
        if operation is None:
            return _text_result(f"Unknown OpenAPI tool: {tool_name}", is_error=True)

        args = dict(arguments or {})
        missing = [
            name for name in operation.input_schema.get("required", []) if name not in args
        ]
        if missing:
            return _text_result(
                "Missing required OpenAPI tool arguments: " + ", ".join(missing),
                is_error=True,
            )
        path = operation.path
        query: list[tuple[str, str, bool]] = []
        request_headers: Dict[str, str] = {}
        cookie_pairs: list[tuple[str, str]] = []
        for parameter in operation.parameters:
            name = parameter["name"]
            if name not in args:
                continue
            value = args[name]
            location = parameter["in"]
            if location == "path":
                path = path.replace(
                    "{" + name + "}",
                    _serialize_path_parameter(parameter, value),
                )
            elif location == "query":
                query.extend(_serialize_query_parameter(parameter, value))
            elif location == "header":
                style = str(parameter.get("style") or "simple")
                if style != "simple":
                    return _text_result(
                        f"Unsupported OpenAPI header parameter style: {style}",
                        is_error=True,
                    )
                request_headers[name] = _simple_value(
                    value,
                    explode=_explode_for(parameter, style),
                )
            elif location == "cookie":
                cookie_pairs.extend(_serialize_cookie_parameter(parameter, value))

        if cookie_pairs:
            request_headers["Cookie"] = "; ".join(
                f"{name}={value}" for name, value in cookie_pairs
            )

        json_body: Any = None
        if operation.body_schema is not None:
            if operation.body_argument is not None:
                if operation.body_argument in args:
                    json_body = args[operation.body_argument]
            elif operation.body_schema.get("type") == "object" or isinstance(
                operation.body_schema.get("properties"), dict
            ):
                body_names = set((operation.body_schema.get("properties") or {}).keys())
                json_body = {name: args[name] for name in body_names if name in args}

        base_url = self._server.base_url.rstrip("/") + "/"
        url = httpx.URL(base_url).join(path.lstrip("/"))
        url = _apply_query(url, query)
        request_kwargs: Dict[str, Any] = {
            "headers": request_headers or None,
        }
        if operation.body_schema is not None and (
            operation.body_argument is None or operation.body_argument in args
        ):
            request_kwargs["json"] = json_body
        try:
            response = await self._server._client.request(
                operation.method,
                url,
                **request_kwargs,
            )
        except httpx.HTTPError as exc:
            return _text_result(f"OpenAPI request failed: {exc}", is_error=True)

        try:
            payload = response.json()
        except (json.JSONDecodeError, ValueError):
            payload = response.text
        if isinstance(payload, str):
            text = payload
        else:
            text = json.dumps(payload, ensure_ascii=False, default=str)

        if response.is_error:
            detail = text[:4000]
            return _text_result(
                f"OpenAPI request returned HTTP {response.status_code}: {detail}",
                is_error=True,
            )
        return _text_result(text)


class OpenAPIServerTask:
    """OpenAPI server adapter compatible with ``mcp_tool.MCPServerTask`` usage."""

    def __init__(self, name: str, *, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.name = name
        self._transport = transport
        self._client: Optional[httpx.AsyncClient] = None
        self._operations: Dict[str, OpenAPIOperation] = {}
        self._tools: list[SimpleNamespace] = []
        self._registered_tool_names: list[str] = []
        self._task = None
        self._error = None
        self._sampling = None
        self._rpc_lock = asyncio.Lock()
        self._inflight_tasks: set = set()
        self._reconnecting = False
        self._pending_call_context = None
        self.session: Optional[OpenAPISession] = None
        self.base_url = ""
        self.tool_timeout = 60.0

    async def start(self, config: dict) -> None:
        if not is_openapi_server_config(config):
            raise ValueError("OpenAPI servers require transport: openapi")
        self.base_url = _validate_http_url(self.name, "url", config.get("url"))
        schema_url = _validate_http_url(
            self.name,
            "openapi_url",
            config.get("openapi_url")
            or self.base_url.rstrip("/") + "/openapi.json",
        )
        headers = config.get("headers") or {}
        if not isinstance(headers, dict):
            raise ValueError("OpenAPI server headers must be an object")

        timeout = config.get("timeout", 60)
        try:
            self.tool_timeout = max(1.0, float(timeout))
        except (TypeError, ValueError):
            self.tool_timeout = 60.0
        connect_timeout = config.get("connect_timeout", 30)
        try:
            connect_timeout = max(1.0, float(connect_timeout))
        except (TypeError, ValueError):
            connect_timeout = 30.0

        self._client = httpx.AsyncClient(
            transport=self._transport,
            headers={str(key): str(value) for key, value in headers.items()},
            timeout=httpx.Timeout(self.tool_timeout, connect=connect_timeout),
            follow_redirects=False,
        )
        try:
            response = await self._client.get(str(schema_url))
            response.raise_for_status()
            document = response.json()
            operations = parse_openapi_operations(document)
        except BaseException:
            await self._client.aclose()
            self._client = None
            raise

        self._operations = {operation.name: operation for operation in operations}
        self._tools = [
            SimpleNamespace(
                name=operation.name,
                description=operation.description,
                inputSchema=operation.input_schema,
                input_schema=operation.input_schema,
                annotations={
                    "readOnlyHint": operation.method in {"GET", "HEAD", "OPTIONS"}
                },
            )
            for operation in operations
        ]
        self.session = OpenAPISession(self)

    async def shutdown(self) -> None:
        client, self._client = self._client, None
        self.session = None
        if client is not None:
            await client.aclose()

    def _is_recycled_stdio(self) -> bool:
        return False

    def mark_tool_call(self) -> None:
        return None
