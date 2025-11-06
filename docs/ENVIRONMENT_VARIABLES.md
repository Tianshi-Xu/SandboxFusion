# SandboxFusion 环境变量说明

本文档整理了 SandboxFusion 服务在运行时可配置的核心环境变量，帮助你在不同部署场景下快速调整行为并排查问题。建议在部署脚本或 CI/CD 管道中设置这些变量，以保证运行时具备可观测性与可控性。

## 1. `SANDBOX_STATS_LOG_EVERY`
- **作用**：控制统计日志按请求次数的打印频率。每当累计的 `/run_code` 请求次数达到该值时，服务会输出一次带成功率和失败原因占比的日志（`sandbox.run_code.stats`）。
- **默认值**：`20`
- **取值示例**：
  - `1`：每个请求都打印一次统计日志，适合本地调试。
  - `100`：每 100 次请求打印一次，适合吞吐较大的线上环境。
- **设置位置**：
  - Docker：`docker run -e SANDBOX_STATS_LOG_EVERY=50 ...`
  - Azure/AML 配置脚本：在 `sing_rl_fast.yml` 或对应任务配置的 `command.env` 中填写。
  - 本地调试：终端直接 `export SANDBOX_STATS_LOG_EVERY=5` 后执行 `make run-online`。

## 2. `SANDBOX_STATS_LOG_SECONDS`
- **作用**：控制统计日志按时间间隔的打印频率。即使没有新的请求达到 count 阈值，也会保证每隔指定秒数输出一次最新统计。
- **默认值**：`60`
- **取值示例**：
  - `10`：每 10 秒至少打印一次，便于实时观察。
  - `0`：禁用按时间触发的统计输出，仅按请求次数触发。
- **设置位置**：同上，可以在容器环境变量、AML 作业 env 或本地 shell 中设置。
- **注意事项**：
  - 当值小于 1 时，系统会强制使用 1 秒作为最小睡眠间隔。
  - 若不希望后台任务运行，可显式设置为 `0` 并把 `SANDBOX_STATS_LOG_EVERY` 设成正数。

## 3. `SANDBOX_LOG_LEVEL`
- **作用**：控制 SandboxFusion 服务的整体日志级别，默认仅打印 INFO 及以上（如成功率统计）。
- **默认值**：`INFO`
- **可选值**：可设置为标准日志级别，如 `DEBUG`/`INFO`/`WARNING` 等。值不区分大小写。
- **设置位置**：
  - 本地：`export SANDBOX_LOG_LEVEL=WARNING`
  - Docker：`-e SANDBOX_LOG_LEVEL=DEBUG`
  - AML：在 `submit_args.env` 中加入 `SANDBOX_LOG_LEVEL: "INFO"`
- **使用建议**：默认 `INFO` 会屏蔽调试输出（如 `request.summary`、`running command ...`）。需要排查细节时再切换到 `DEBUG`。

## 4. `VERL_TOOL_PARSER_ENABLE_REPAIR`
- **作用**：控制 Hermes 工具解析器是否启用 JSON 修复/容错逻辑。在训练阶段可关闭，使模型对格式错误负责；在线上可保持开启降低失败率。
- **默认值**：`1`（开启容错）
- **可选值**：
  - `1` / `true` / `True`：启用修复逻辑（默认）。
  - `0` / `false` / `False`：严格模式，不修复非法 JSON，解析失败会直接返回空并记录错误日志。
- **设置位置**：
  - 训练脚本或 RL 任务：在启动命令前 `export VERL_TOOL_PARSER_ENABLE_REPAIR=0`。
  - 线上服务：保持默认或在 Docker/AML 环境变量中显式设为 `1`。
- **生效范围**：`verl/experimental/agent_loop/tool_parser.py` 中的 HermesToolParser 会读取该值。

## 5. 设置示例
### 备选方案 A：Azure AML 作业（`sing_rl_fast.yml`）
```yaml
jobs:
- name: open-agentrl-qwen3-4b-rl-test
  submit_args:
    env:
      SANDBOX_STATS_LOG_EVERY: "10"
      SANDBOX_STATS_LOG_SECONDS: "30"
  VERL_TOOL_PARSER_ENABLE_REPAIR: "0"
  SANDBOX_LOG_LEVEL: "INFO"
```

### 备选方案 B：本地调试
```bash
export SANDBOX_STATS_LOG_EVERY=5
export SANDBOX_STATS_LOG_SECONDS=15
export VERL_TOOL_PARSER_ENABLE_REPAIR=0
export SANDBOX_LOG_LEVEL=INFO
make run-online
```

### 备选方案 C：Docker 启动
```bash
docker run \
  -e SANDBOX_STATS_LOG_EVERY=50 \
  -e SANDBOX_STATS_LOG_SECONDS=60 \
  -e VERL_TOOL_PARSER_ENABLE_REPAIR=1 \
  -e SANDBOX_LOG_LEVEL=INFO \
  sandbox:server
```

---

若未来新增环境变量，请同步维护此文档。可在 `SandboxFusion` 目录下运行 `grep -R "os.getenv"` 快速排查现有配置点。
