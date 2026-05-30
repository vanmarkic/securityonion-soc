"""Salt relay seam — the file-based queue used to reach SaltStack.

SaltStack is reached via a file-based relay queue (no salt library/subprocess):
``exec_command`` writes the args dict as JSON to ``<queue_dir>/<command_id>``,
then polls for ``<queue_dir>/<command_id>.response`` until it appears or the
timeout elapses. Ported from server/modules/salt/saltstore.go (execCommand).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Protocol, runtime_checkable


class SaltRelayDown(Exception):
    """Raised when the relay does not produce a response before the timeout."""

    def __init__(self, message: str = "ERROR_SALT_RELAY_DOWN") -> None:
        super().__init__(message)


@runtime_checkable
class SaltRelayClient(Protocol):
    async def exec_command(
        self, command_id: str, args: dict[str, str], *, timeout_ms: int | None = None
    ) -> str: ...


class FakeRelayClient:
    """In-memory relay returning canned responses keyed by ``args["command"]``."""

    def __init__(self, responses: dict[str, str]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    async def exec_command(
        self, command_id: str, args: dict[str, str], *, timeout_ms: int | None = None
    ) -> str:
        self.calls.append((command_id, args))
        command = args["command"]
        if command not in self._responses:
            raise KeyError(f"no canned response for command {command!r}")
        return self._responses[command]


class FileQueueRelayClient:
    """Real relay client backed by the file-based queue directory."""

    def __init__(self, queue_dir: str, timeout_ms: int = 30_000) -> None:
        self.queue_dir = queue_dir
        self.timeout_ms = timeout_ms

    async def exec_command(
        self, command_id: str, args: dict[str, str], *, timeout_ms: int | None = None
    ) -> str:
        queue = Path(self.queue_dir)
        queue.mkdir(parents=True, exist_ok=True)

        request_file = queue / command_id
        # Inject command_id into the payload without mutating the caller's dict,
        # matching Go execCommand (args["command_id"] = id before writing).
        payload = {**args, "command_id": command_id}
        request_file.write_text(json.dumps(payload))

        response_file = queue / f"{command_id}.response"
        effective_timeout_ms = max(self.timeout_ms, timeout_ms or 0)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + effective_timeout_ms / 1000
        while loop.time() < deadline:
            if response_file.exists():
                response = response_file.read_text().strip()
                response_file.unlink()
                return response
            # Very short timeouts are used for testing, where the response is
            # already mocked; skip the inter-poll sleep in that case. Gate on the
            # instance timeout, matching Go's instance-level guard (store.timeoutMs > 10).
            if self.timeout_ms > 10:
                await asyncio.sleep(1)

        raise SaltRelayDown
