# CareFund-AI

CareFund-AI 是面向医疗求助场景的 AI 原生 Web 应用。系统把申请信息、医疗材料和用户确认组织为可追溯事实，通过 OCR、LLM 工作流和确定性校验生成受证据约束的求助草稿，避免 AI 擅自补写病情、费用或证明材料。

本项目参加第九届传智杯全国大学生数智创新与 AI 应用大赛“AI WEB 网页开发挑战赛”。作品以 React Web 应用为主要呈现形态，AI 信息抽取、追问与草稿生成是核心流程；后端负责材料处理、状态编排和安全门禁。

## 核心能力

- 三步收集患者基本信息、医疗情况和资金情况。
- 上传 PDF、JPEG、PNG，执行本地文本提取与 OCR。
- 使用 Dify 工作流调用大模型，抽取候选事实并提出补充问题。
- 对事实、证据引用、金额、日期、冲突和用户确认执行确定性校验。
- 仅使用通过校验的事实生成草稿，并在确认、导出前再次核验版本和内容。
- 以 JSON 申请资料包导出完整的事实、证据、校验与确认记录。

## 技术架构

```text
React + TypeScript + Vite
          │ REST /api/v1
          ▼
FastAPI + SQLite ── 本地 OCR / PDF 文本提取
          ├──────── Dify LLM 工作流（抽取、追问、草稿）
          └──────── Validation（证据、冲突、阶段门禁）
```

主要目录：

- `frontend/`：React、TypeScript、Tailwind CSS、Vitest。
- `backend/`：FastAPI、SQLite、OCR、任务编排与导出。
- `agent/`：Dify 调用、Schema 边界与模型输出约束。
- `validation/`：确定性事实、证据和最终化校验。
- `contracts/`：OpenAPI、JSON Schema 和虚构示例。
- `docs/`：参赛开发规范与正式业务 Policy。

## 本地运行

后端需要 Python 3.10+：

```powershell
python -m venv backend/.venv
& backend/.venv/Scripts/python.exe -m pip install -r backend/requirements.txt
Copy-Item backend/.env.example backend/.env
& backend/.venv/Scripts/python.exe -m uvicorn backend.main:app --reload
```

前端需要 Node.js 22 LTS 和 npm：

```powershell
Set-Location frontend
npm ci
npm run dev
```

前端默认打开 `http://localhost:5173`，后端 API 文档位于 `http://127.0.0.1:8000/docs`。Dify 密钥只通过后端环境变量提供，禁止放入 `VITE_` 变量或提交到仓库。

## 环境变量

以 `backend/.env.example` 和 `frontend/.env.example` 为模板。至少需要配置：

- `DIFY_BASE_URL`
- `DIFY_EXTRACT_API_KEY`
- `DIFY_DRAFT_API_KEY`
- `CAREFUND_VALIDATION_POLICY`
- `CAREFUND_DATA_DIR`
- `VITE_API_BASE_URL`

公开仓库不得包含真实 API 密钥、患者数据或未脱敏材料。

## 测试

```powershell
& backend/.venv/Scripts/python.exe -m pytest backend/tests validation/tests contracts/tests agent/tests -q
Set-Location frontend
npm run typecheck
npm test -- --run
npm run build
```

正式校验规则见 [CareFund V1 Policy](docs/VALIDATION_POLICY.md)。该规则约束 AI 生成和资料完整性，不构成医疗诊断、材料真伪认证或真实筹款平台审批。

## 责任边界

CareFund-AI 是申请资料整理与风险提示工具，不提供医疗诊断，不判断材料真伪，不承诺筹款审核或筹款结果。所有模型输出均为候选内容，必须经过 Schema 校验、证据核对、用户确认和版本门禁。

## 团队成员

马悠原：西安交通大学计算机越杰2401班学生
许家铭：西安交通大学工业工程2501班学生
