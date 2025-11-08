# Copyright 2024 Bytedance Ltd. and/or its affiliates
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import asyncio
from unittest.mock import AsyncMock

import pytest

from sandbox.runners.base import run_command_bare
from sandbox.runners.types import CommandRunStatus


class _DummyStream:
    def __init__(self) -> None:
        self._closed = False

    def is_closing(self) -> bool:
        return True

    def write(self, data: bytes) -> None:  # pragma: no cover - safety net
        raise AssertionError("write should not be called when stream is closing")

    def close(self) -> None:
        self._closed = True

    async def wait_closed(self) -> None:
        return


class _DummyProcess:
    def __init__(self) -> None:
        self.stdin = _DummyStream()
        self.stdout = object()
        self.stderr = object()
        self.returncode = None
        self.pid = 424242

    async def wait(self) -> None:
        self.returncode = 0
        return


@pytest.mark.asyncio
async def test_run_command_bare_skips_write_when_stdin_closing(monkeypatch):
    dummy_process = _DummyProcess()

    async def _fake_create_subprocess_shell(*_args, **_kwargs):
        return dummy_process

    monkeypatch.setattr(asyncio, "create_subprocess_shell", _fake_create_subprocess_shell)
    monkeypatch.setattr(asyncio, "create_subprocess_exec", _fake_create_subprocess_shell)

    monkeypatch.setattr("sandbox.runners.base.get_output_non_blocking", AsyncMock(return_value=""))
    monkeypatch.setattr("sandbox.runners.base.psutil.pid_exists", lambda _pid: False)
    monkeypatch.setattr("sandbox.runners.base.kill_process_tree", lambda _pid: None)
    monkeypatch.setattr("sandbox.runners.base.cleanup_process", lambda: None)
    monkeypatch.setattr("sandbox.runners.base.ensure_bash_integrity", lambda: None)

    result = await run_command_bare("echo 'hi'", stdin="payload")

    assert result.status == CommandRunStatus.Finished
    assert result.return_code == 0
    assert dummy_process.stdin._closed is True
