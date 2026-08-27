"""Contract tests for the direct POSIX stdio MCP child watchdog."""

import os
import sys

import pytest

from tools import mcp_stdio_watchdog, mcp_tool


def test_is_orphaned_is_false_while_direct_parent_is_unchanged():
    original_ppid = 1234

    assert mcp_stdio_watchdog._is_orphaned(
        original_ppid,
        getppid=lambda: original_ppid,
    ) is False


@pytest.mark.skipif(os.name != "posix", reason="watchdog wrapping is POSIX-only")
def test_wrap_command_uses_stable_parent_pid_and_preserves_command_tail():
    parent_pid = os.getpid()
    command = "/opt/hermes/bin/mcp-server"
    command_args = ["--label", "value with spaces", "--", "literal-tail"]

    wrapped_command, wrapped_args = mcp_tool._wrap_command_with_watchdog(
        command,
        command_args,
    )

    assert wrapped_command == sys.executable
    assert wrapped_args == [
        os.path.join(os.path.dirname(mcp_tool.__file__), "mcp_stdio_watchdog.py"),
        "--ppid",
        str(parent_pid),
        "--",
        command,
        *command_args,
    ]
    assert "--create-time" not in wrapped_args


def test_stdio_children_dead_is_false_when_a_tracked_child_is_alive(monkeypatch):
    """A live stdio child must not trigger the fast-fail watchdog."""
    server = mcp_tool.MCPServerTask("stdio")
    server._stdio_child_pids = {101}
    fake_psutil = type(
        "Psutil", (), {"pid_exists": staticmethod(lambda pid: pid == 101)}
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    assert server._stdio_children_dead() is False


def test_stdio_children_dead_is_true_after_all_tracked_children_exit(monkeypatch):
    """The watchdog still detects an exited stdio child."""
    server = mcp_tool.MCPServerTask("stdio")
    server._stdio_child_pids = {101, 102}
    fake_psutil = type(
        "Psutil", (), {"pid_exists": staticmethod(lambda pid: False)}
    )
    monkeypatch.setitem(sys.modules, "psutil", fake_psutil)

    assert server._stdio_children_dead() is True
