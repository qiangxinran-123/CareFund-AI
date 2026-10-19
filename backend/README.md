# CareFund-AI Backend

FastAPI V1 后端，严格使用仓库 `contracts/` 中已经确认的接口路径和字段。当前提供可运行的内存版本，OCR 已使用本地实现；Agent 和 Validation 通过适配器接入其他成员的模块。

## 当前能力

- 创建、读取和修订申请
- 上传 PDF/JPEG/PNG（单文件最大 10 MiB）
- 本地图片 OCR（RapidOCR + ONNX Runtime，不上传第三方服务）
- PDF 原生文本提取；扫描页自动转图片后 OCR
- 对接 A 的正式 AgentService（Dify 工作流）
- 对接 D 的正式事实校验、确认前校验和导出前校验
- 分析任务、草稿生成、确认与 JSON 导出流程
- 统一契约错误响应及 revision 并发保护

内存数据会在服务重启后清空。OCR 只负责提取材料中可见的文字，不代表验证了材料真实性；识别结果仍须经过事实校验和人工确认。单个 PDF 最多处理 20 页，第一次识别图片时需要加载本地模型，耗时会比后续调用长。

## 本地运行

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload
```

正式联调前复制 `backend/.env.example` 中的配置到本机环境变量，并填写 A 提供的两个 Dify API Key。密钥不得提交到 Git。`CAREFUND_VALIDATION_POLICY` 当前指向联调用规则，正式必填字段和材料清单仍需团队确认。

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
