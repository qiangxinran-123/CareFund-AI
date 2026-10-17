# CareFund-AI 前端

已完成第二阶段申请信息填写流程。技术栈：React、Vite、TypeScript（strict）、Tailwind CSS、原生 Fetch API、Vitest 和 React Testing Library。

## 环境与命令

需要 Node.js 20.19+ 或 22.12+（建议当前 LTS）及 npm。PowerShell 若禁止执行 `npm.ps1`，可使用 `npm.cmd`。

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run test -- --run
npm run build
```

开发服务器默认地址为 `http://localhost:5173`。

## 配置与目录

复制 `.env.example` 为 `.env.local`，按需设置公开的 `VITE_API_BASE_URL`。默认值为 `/api/v1`，与 `contracts/openapi.yaml` 一致。跨源联调时可填写后端完整地址及 `/api/v1` 前缀；密钥和服务端 Token 不得放在 `VITE_` 环境变量中。

后端不可用时，可在 `.env.local` 设置 `VITE_USE_MOCK_API=true`。页面会明确显示 Mock 标识；Mock 仅保存在当前 JavaScript 运行环境中，不代表真实后端持久化。浏览器存储只记录不透明的 `application_id`，不保存病情自述。

- `src/api/`：统一 Fetch 请求、JSON 和错误处理。
- `src/components/layout/`：可复用页面布局和流程展示。
- `src/features/application/`：三步申请表单、集中校验和交互测试。
- `src/types/`：当前需要的契约类型。
- `src/mocks/`：从 `contracts/examples/application.example.json` 复制的虚构样例，仅供测试与后续开发。
- `src/styles/`：基础样式及 Tailwind 入口。

`pages/` 和 `hooks/` 将在出现独立路由页面或可复用自定义 Hook 时建立，避免空目录。

## 当前范围与接口

已完成基本信息、医疗情况、资金情况三步导航，及创建、更新和恢复申请的 API 调用。当前正式申请契约仅包含 `display_name`、`age_group`、`medical_summary`；资金字段、治疗时间和费用尚未定义，因此资金步骤只显示契约缺口，不收集或提交自创字段。

材料上传、OCR、AI 分析、追问、草稿确认和导出均未实现。

前端后续仅调用 FastAPI 的 `/api/v1` REST 接口。公共路径、请求与响应结构以仓库 `contracts/openapi.yaml` 和 `contracts/schemas/` 为准。业务 Mock 不参与生产页面逻辑，也不代表真实后端响应。

