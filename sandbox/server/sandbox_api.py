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

import os
import traceback
<<<<<<< HEAD
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog
from fastapi import APIRouter
=======
import uuid
from enum import Enum
from typing import Dict, List, Optional, Tuple

import structlog  # type: ignore[import-not-found]
from fastapi import APIRouter, Request
>>>>>>> rescue
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
        req_logger.info(
            'sandbox.run_code.start',
            language=payload.language,
            compile_timeout=payload.compile_timeout,
            run_timeout=payload.run_timeout,
            memory_limit_mb=payload.memory_limit_MB,
            code_preview=payload.code[:120],
            files=list(payload.files.keys()),
        )
        result = await CODE_RUNNERS[payload.language](CodeRunArgs(**payload.model_dump()))

        resp.compile_result = result.compile_result
        resp.run_result = result.run_result
        resp.files = result.files
        resp.status, message = parse_run_status(result)
        if resp.status == RunStatus.SandboxError:
            resp.message = message
        compile_status = result.compile_result.status if result.compile_result else None
        compile_duration = result.compile_result.execution_time if result.compile_result else None
        run_status = result.run_result.status if result.run_result else None
        run_duration = result.run_result.execution_time if result.run_result else None
        req_logger.info(
            'sandbox.run_code.finish',
            status=resp.status,
            compile_status=compile_status,
            compile_duration=compile_duration,
            run_status=run_status,
            run_duration=run_duration,
            message=resp.message,
        )
    except Exception as e:
        message = f'exception on running code {payload.code}: {e} {traceback.print_tb(e.__traceback__)}'
        req_logger.warning('sandbox.run_code.exception', error=str(e))
        resp.message = message
        resp.status = RunStatus.SandboxError

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
