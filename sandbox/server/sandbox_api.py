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
import os
import re
import time
import traceback
import uuid
from collections import Counter
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import structlog  # type: ignore[import-not-found]
from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from sandbox.runners import (
    CODE_RUNNERS,
    CellRunResult,
    CodeRunArgs,
    CodeRunResult,
    CommandRunResult,
    CommandRunStatus,
    Language,
    RunJupyterRequest,
    run_jupyter,
)

sandbox_router = APIRouter()
logger = structlog.stdlib.get_logger()

_STATS_LOCK: asyncio.Lock = asyncio.Lock()
_STATUS_COUNTER: Counter[str] = Counter()
_REASON_COUNTER: Counter[str] = Counter()
_LAST_LOG_TS: float = 0.0
_STATS_TASK: asyncio.Task | None = None
_STOP_EVENT: asyncio.Event | None = None
_LOG_EVERY_REQUESTS: int = int(os.getenv("SANDBOX_STATS_LOG_EVERY", "200"))
_LOG_EVERY_SECONDS: float = float(os.getenv("SANDBOX_STATS_LOG_SECONDS", "0"))
_LAST_IMPORT_FAILURE: dict[str, str] | None = None

_IMPORT_ERROR_PATTERN = re.compile(r"(ModuleNotFoundError: No module named '([^']+)')|(ImportError: .+)")


def _classify_run_code_reason(resp: "RunCodeResponse") -> str:
    """根据响应信息推断失败原因标签。"""
    if resp.status == RunStatus.Success:
        return "success"
    if resp.status == RunStatus.SandboxError:
        return "sandbox_error"

    compile_result = resp.compile_result
    run_result = resp.run_result

    if compile_result:
        if compile_result.status == CommandRunStatus.TimeLimitExceeded:
            return "compile_timeout"
        if _IMPORT_ERROR_PATTERN.search((compile_result.stderr or "")):
            return "import_error"
        if compile_result.status == CommandRunStatus.Error:
            return "compile_error"
        if compile_result.return_code not in (None, 0):
            return "compile_non_zero_exit"

    if run_result:
        if run_result.status == CommandRunStatus.TimeLimitExceeded:
            return "run_timeout"
        if run_result.status == CommandRunStatus.Error:
            if _IMPORT_ERROR_PATTERN.search((run_result.stderr or "")):
                return "import_error"
            return "run_runtime_error"
        if _IMPORT_ERROR_PATTERN.search((run_result.stderr or "")):
            return "import_error"
        if run_result.return_code not in (None, 0):
            return "run_non_zero_exit"

    return "failed_unknown"


async def _emit_stats(force: bool = False, logger_to_use: Any | None = None) -> None:
    """在满足条件时输出统计信息。"""
    global _LAST_LOG_TS
    if logger_to_use is None:
        logger_to_use = logger

    async with _STATS_LOCK:
        total = _STATUS_COUNTER.get("total", 0)
        if total == 0:
            return

        now = time.time()
        by_count = _LOG_EVERY_REQUESTS > 0 and total % _LOG_EVERY_REQUESTS == 0
        by_time = _LOG_EVERY_SECONDS > 0 and (now - _LAST_LOG_TS) >= _LOG_EVERY_SECONDS

        if not force and not by_count and not by_time:
            return

        success = _STATUS_COUNTER.get("success", 0)
        failed = _STATUS_COUNTER.get("failed", 0)
        sandbox_error = _STATUS_COUNTER.get("sandbox_error", 0)
        success_rate = success / total if total else 0.0
        failure_breakdown = {
            k: {
                "count": v,
                "ratio": round(v / total, 4),
            }
            for k, v in _REASON_COUNTER.items()
            if k != "success"
        }
        logger_to_use.warn(
            "sandbox.run_code.stats",
            total_requests=total,
            success_count=success,
            failed_count=failed,
            sandbox_error_count=sandbox_error,
            success_rate=round(success_rate, 4),
            failure_breakdown=failure_breakdown,
            import_error_example=_LAST_IMPORT_FAILURE,
        )
        _LAST_LOG_TS = now


async def _record_status(status: "RunStatus", reason: str, req_logger: Any) -> None:
    """记录请求状态并周期性输出成功率统计。"""
    async with _STATS_LOCK:
        _STATUS_COUNTER["total"] += 1
        if status == RunStatus.Success:
            status_key = "success"
        elif status == RunStatus.Failed:
            status_key = "failed"
        else:
            status_key = "sandbox_error"
        _STATUS_COUNTER[status_key] += 1
        _REASON_COUNTER[reason] += 1

    await _emit_stats(logger_to_use=req_logger)


async def _update_import_failure(example: dict[str, str]) -> None:
    async with _STATS_LOCK:
        global _LAST_IMPORT_FAILURE
        _LAST_IMPORT_FAILURE = example


def _extract_import_failure(
    code: str,
    language: str,
    compile_result: Optional[CommandRunResult],
    run_result: Optional[CommandRunResult],
) -> Optional[dict[str, str]]:
    def _match_error(result: Optional[CommandRunResult]) -> Optional[tuple[str, str]]:
        if result is None:
            return None
        stderr = (result.stderr or "").strip()
        match = _IMPORT_ERROR_PATTERN.search(stderr)
        if not match:
            return None
        error_line = match.group(0)
        module_name = match.group(2) or ""
        return error_line, module_name

    for candidate in (compile_result, run_result):
        matched = _match_error(candidate)
        if matched:
            error_line, module_name = matched
            return {
                "language": language,
                "module": module_name,
                "error": error_line,
                "code_preview": code[:200],
            }
    return None


async def _stats_loop(stop_event: asyncio.Event) -> None:
    try:
        while True:
            await asyncio.sleep(max(_LOG_EVERY_SECONDS, 1.0))
            if stop_event.is_set():
                break
            await _emit_stats(force=True)
    except asyncio.CancelledError:  # pragma: no cover - shutdown
        pass


def start_stats_background_task() -> None:
    global _STATS_TASK, _STOP_EVENT
    if _LOG_EVERY_SECONDS <= 0:
        return
    if _STATS_TASK and not _STATS_TASK.done():
        return
    loop = asyncio.get_running_loop()
    _STOP_EVENT = asyncio.Event()
    _STATS_TASK = loop.create_task(_stats_loop(_STOP_EVENT))


async def stop_stats_background_task() -> None:
    global _STATS_TASK, _STOP_EVENT
    if _STOP_EVENT:
        _STOP_EVENT.set()
    if _STATS_TASK:
        _STATS_TASK.cancel()
        try:
            await _STATS_TASK
        except asyncio.CancelledError:  # pragma: no cover - shutdown
            pass
    _STATS_TASK = None
    _STOP_EVENT = None


class RunCodeRequest(BaseModel):
    compile_timeout: float = Field(10, description='compile timeout for compiled languages')
    run_timeout: float = Field(10, description='code run timeout')
    memory_limit_MB: int = Field(-1, description='maximum memory allowed in megabytes')
    code: str = Field(..., examples=['print("hello")'], description='the code to run')
    stdin: Optional[str] = Field(None, examples=[''], description='optional string to pass into stdin')
    language: Language = Field(..., examples=['python'], description='the language or execution mode to run the code')
    files: Dict[str, Optional[str]] = Field({}, description='a dict from file path to base64 encoded file content')
    fetch_files: List[str] = Field([], description='a list of file paths to fetch after code execution')


class RunStatus(str, Enum):
    # all command finished successfully
    Success = 'Success'
    # one of the process has non-zero return code
    Failed = 'Failed'
    # error on sandbox side
    SandboxError = 'SandboxError'


class RunCodeResponse(BaseModel):
    status: RunStatus
    message: str
    compile_result: Optional[CommandRunResult] = None
    run_result: Optional[CommandRunResult] = None
    executor_pod_name: Optional[str] = None
    files: Dict[str, str] = {}


class RunJupyterResponse(BaseModel):
    status: RunStatus
    message: str
    driver: Optional[CommandRunResult] = None
    cells: List[CellRunResult] = []
    executor_pod_name: Optional[str] = None
    files: Dict[str, str] = {}


def parse_run_status(result: CodeRunResult) -> Tuple[RunStatus, str]:
    outcomes = []
    retcodes = []
    err_msgs = []
    if result.compile_result is not None:
        outcomes.append(result.compile_result.status)
        err_msgs.append(result.compile_result.stderr or '')
        if result.compile_result.return_code is not None:
            retcodes.append(result.compile_result.return_code)
    if result.run_result is not None:
        outcomes.append(result.run_result.status)
        err_msgs.append(result.run_result.stderr or '')
        if result.run_result.return_code is not None:
            retcodes.append(result.run_result.return_code)

    for o, m in zip(outcomes, err_msgs):
        if o == CommandRunStatus.Error:
            return RunStatus.SandboxError, m
    if any([o == CommandRunStatus.TimeLimitExceeded for o in outcomes]):
        return RunStatus.Failed, ''
    if any([r != 0 for r in retcodes]):
        return RunStatus.Failed, ''
    # no error, no tle and no non-zero return codes -> success
    return RunStatus.Success, ''


@sandbox_router.post("/run_code", response_model=RunCodeResponse, tags=['sandbox'])
async def run_code(payload: RunCodeRequest, http_request: Request):
    request_id = http_request.headers.get('x-request-id') or str(uuid.uuid4())
    req_logger = logger.bind(request_id=request_id)
    resp = RunCodeResponse(status=RunStatus.Success, message='', executor_pod_name=os.environ.get('MY_POD_NAME'))
    try:
        # req_logger.info(
        #     'sandbox.run_code.start',
        #     language=payload.language,
        #     compile_timeout=payload.compile_timeout,
        #     run_timeout=payload.run_timeout,
        #     memory_limit_mb=payload.memory_limit_MB,
        #     code_preview=payload.code[:120],
        #     files=list(payload.files.keys()),
        # )
        result = await CODE_RUNNERS[payload.language](CodeRunArgs(**payload.model_dump()))

        resp.compile_result = result.compile_result
        resp.run_result = result.run_result
        resp.files = result.files
        resp.status, message = parse_run_status(result)
        if resp.status == RunStatus.SandboxError:
            resp.message = message
        # compile_status = result.compile_result.status if result.compile_result else None
        # compile_duration = result.compile_result.execution_time if result.compile_result else None
        # run_status = result.run_result.status if result.run_result else None
        # run_duration = result.run_result.execution_time if result.run_result else None
        # req_logger.info(
        #     'sandbox.run_code.finish',
        #     status=resp.status,
        #     compile_status=compile_status,
        #     compile_duration=compile_duration,
        #     run_status=run_status,
        #     run_duration=run_duration,
        #     message=resp.message,
        # )
    except Exception as e:
        message = f'exception on running code {payload.code}: {e} {traceback.print_tb(e.__traceback__)}'
        req_logger.warning('sandbox.run_code.exception', error=str(e))
        resp.message = message
        resp.status = RunStatus.SandboxError

    reason = _classify_run_code_reason(resp)
    language_value = getattr(payload.language, "value", payload.language)
    import_failure = _extract_import_failure(
        payload.code,
        str(language_value),
        resp.compile_result,
        resp.run_result,
    )
    if import_failure:
        await _update_import_failure(import_failure)
    await _record_status(resp.status, reason, req_logger)
    return resp


@sandbox_router.post("/run_jupyter", name='Run Code in Jupyter', response_model=RunJupyterResponse, tags=['sandbox'])
async def run_jupyter_handler(payload: RunJupyterRequest, http_request: Request):
    request_id = http_request.headers.get('x-request-id') or str(uuid.uuid4())
    req_logger = logger.bind(request_id=request_id)
    resp = RunJupyterResponse(status=RunStatus.Success, message='', executor_pod_name=os.environ.get('MY_POD_NAME'))
    code_repr = "\n".join(payload.cells)[:100]
    try:
        req_logger.info(
            'sandbox.run_jupyter.start',
            code_preview=code_repr,
            files=list(payload.files.keys()),
        )
        result = await run_jupyter(payload)
        resp.driver = result.driver
        if result.status != CommandRunStatus.Finished:
            resp.status = RunStatus.Failed
        else:
            resp.status = RunStatus.Success
            resp.cells = result.cells
            resp.files = result.files
        req_logger.info(
            'sandbox.run_jupyter.finish',
            status=resp.status,
            driver_status=result.status if result else None,
        )
    except Exception as e:
        message = f'exception on running jupyter {code_repr}: {e} {traceback.print_tb(e.__traceback__)}'
        req_logger.warning('sandbox.run_jupyter.exception', error=str(e))
        resp.message = message
        resp.status = RunStatus.SandboxError

    return resp
