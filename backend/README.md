# CareFund-AI Backend

FastAPI 后端负责申请状态、文件处理、AI 调用编排、确定性校验和可下载 JSON 资料包。它是 Application、revision、附件集合、分析结果和草稿状态的唯一权威来源。

## 能力

- 创建、读取和修订申请，持久化基本、医疗和资金信息。
- 接收 PDF、JPEG、PNG，单文件最大 10 MiB。
- 本地图片 OCR；PDF 优先提取原生文本，扫描页转图片后 OCR。
- 后台执行 AI 分析任务并提供轮询状态。
- 调用 Agent 完成候选事实、补充问题和受约束草稿生成。
- 调用 Validation 完成分析、确认和导出前校验。
- SQLite 持久化、幂等上传/分析、revision 并发保护和旧结果失效。

## 正式 Policy

默认加载 `backend/config/validation-policy.v1.json`。该规则已经冻结：

- 必填：病情自述、预计后续治疗费用。
- 预计费用必须有材料来源；至少一份材料完成解析。
- 必填事实必须由用户确认。
- 冲突、无依据事实、失效引用、提示注入和版本不一致均阻断。
- 建议项 warning 与用户来源 info 保留展示，但不单独阻断。

完整规则和生成、确认、导出门禁见 [`docs/VALIDATION_POLICY.md`](../docs/VALIDATION_POLICY.md)。可用 `CAREFUND_VALIDATION_POLICY` 指定其他文件进行测试，但提交演示必须使用 V1 正式规则。

## 本地运行

```powershell
python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
& backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --reload
```

Swagger UI：`http://127.0.0.1:8000/docs`。

`backend/.env.example` 只包含变量名和安全默认值。Dify 密钥不得提交；服务不会自动把失败切换成 Mock 成功。测试时可显式设置：

```powershell
$env:CAREFUND_AGENT_MODE="mock"
$env:CAREFUND_VALIDATION_MODE="mock"
```

## 数据与隐私

默认数据目录为 `backend/instance/`，包含 SQLite、上传文件和导出资料包，已从 Git 排除。OCR 只提取可见文字，不认证材料真伪。单个 PDF 最多处理 20 页。当前后台任务执行器面向单进程演示，多 Worker 不共享内存任务队列。

上传必须携带 `Idempotency-Key`。网络重试复用原键；同申请下同键不同文件返回 409。`POST /analyze` 返回 202，客户端轮询任务状态后读取分析结果。

## 测试

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests validation/tests contracts/tests -q
```

导出包包含契约化申请、材料元数据、Evidence、Fact、分析结果、已确认草稿和最终校验结果，不包含原始上传文件字节。
