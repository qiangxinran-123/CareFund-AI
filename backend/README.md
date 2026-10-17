# CareFund-AI Backend

FastAPI V1 基础框架，严格使用仓库 `contracts/` 中已经确认的接口路径和字段。当前提供可运行的内存版本，并以确定性 Mock 适配器代替尚未接入的 OCR、Agent 和 Validation 模块。

## 当前能力

- 创建、读取和修订申请
- 上传 PDF/JPEG/PNG（单文件最大 10 MiB）
- Mock OCR 文本提取
- Mock Agent 事实整理和追问
- Mock 确定性校验
- 分析任务、草稿生成、确认与 JSON 导出流程
- 统一契约错误响应及 revision 并发保护

内存数据会在服务重启后清空；Mock OCR 只返回占位文本，不能用于真实材料识别或真实性判断。

## 本地运行

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python -m uvicorn backend.main:app --reload
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

- OCR：替换 `backend/services/ocr.py` 中的适配器实现。
- Agent：让 A 模块实现与 `MockAgentService.extract`、`draft_sections` 等价的输入输出边界。
- Validation：让 D 模块实现与 `MockValidationService.validate` 等价的输入输出边界。

接入时不应修改对外 API；如公共字段确需变化，必须先由相关成员共同确认并更新 `contracts/`。
