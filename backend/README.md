# CareFund-AI Backend

FastAPI V1 后端，严格使用仓库 `contracts/` 中已经确认的接口路径和字段。当前提供适合单机演示的本地持久化版本，OCR 已使用本地实现；Agent 和 Validation 通过适配器接入其他成员的模块。

## 当前能力

- 创建、读取和修订申请
- 上传 PDF/JPEG/PNG（单文件最大 10 MiB）
- 本地图片 OCR（RapidOCR + ONNX Runtime，不上传第三方服务）
- PDF 原生文本提取；扫描页自动转图片后 OCR
- 对接 A 的正式 AgentService（Dify 工作流）
- 对接 D 的正式事实校验、确认前校验和导出前校验
- 真正后台执行的分析任务、轮询、草稿生成、确认与可下载 JSON 导出流程
- 上传与分析请求幂等保护
- SQLite 申请状态和本地上传文件持久化
- 统一契约错误响应及 revision 并发保护

默认数据目录为 `backend/instance/`，也可用 `CAREFUND_DATA_DIR` 指向其他受控本地目录。该目录包含 SQLite 文件、上传材料和已生成的 JSON 资料包，不应提交到 Git。服务重启时，已完成的申请、分析和草稿会恢复；已生成资料包的下载地址也继续有效。重启时仍处于 `queued` 或 `running` 的分析任务会标记为失败，需要用户重新发起。当前后台执行器面向单进程、单 Worker 演示，多 Worker 之间不共享任务执行队列。

OCR 只负责提取材料中可见的文字，不代表验证了材料真实性；识别结果仍须经过事实校验和人工确认。单个 PDF 最多处理 20 页，第一次识别图片时需要加载本地模型，耗时会比后续调用长。

## 本地运行

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload
```

正式联调前复制 `backend/.env.example` 中的配置到本机环境变量，并填写 A 提供的两个 Dify API Key。密钥不得提交到 Git。`CAREFUND_VALIDATION_POLICY` 当前指向联调用规则，正式必填字段和材料清单仍需团队确认。

上传接口必须携带 `Idempotency-Key` Header。一次新上传生成一个新键；网络重试必须复用原键。同一申请下，同键同文件返回已有文档，同键不同文件返回 409。

`POST /analyze` 只创建任务并返回 202。客户端应使用返回的 `job_id` 轮询 `/analysis/jobs/{job_id}`，直到状态进入 `succeeded` 或 `failed`，再读取最新分析结果。

导出成功时，`POST /applications/{application_id}/export` 返回非空 `download_url`。该地址提供 UTF-8 JSON 申请资料包，并以附件形式下载；资料包只包含契约化申请、材料元数据、证据、事实、分析、已确认草稿和最终导出校验结果，不包含原始上传文件字节。

若只运行后端自动测试，可显式设置：

```powershell
$env:CAREFUND_AGENT_MODE="mock"
$env:CAREFUND_VALIDATION_MODE="mock"
```

服务启动后：

- 健康检查：`GET http://127.0.0.1:8000/api/v1/health`
- Swagger UI：`http://127.0.0.1:8000/docs`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## 测试

```powershell
python -m pytest backend\tests -q
python -m unittest contracts.tests.test_contracts
```

## 后续真实模块接入点

- OCR：正式实现位于 `backend/services/ocr.py`，后续可在不修改路由的前提下更换模型。
- Agent：正式适配器调用 `agent.AgentService`；缺少 Dify 配置时分析接口会明确返回依赖不可用。
- Validation：正式适配器调用 D 的分析、确认和导出校验入口；联调规则位于 `backend/config/`。

接入时不应修改对外 API；如公共字段确需变化，必须先由相关成员共同确认并更新 `contracts/`。
