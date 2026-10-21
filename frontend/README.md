# CareFund-AI 前端

提供四步申请流程：申请信息、医疗材料上传、信息核对与补充、草稿确认及导出。技术栈：React、Vite、TypeScript（strict）、Tailwind CSS、原生 Fetch API、Vitest 和 React Testing Library。

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

复制 `.env.example` 为 `.env.local`，按需设置公开的 `VITE_API_BASE_URL`。本地真实联调使用 `/api/v1`，与 `contracts/openapi.yaml` 一致；Vite 会将 `/api` 转发到 `http://127.0.0.1:8000`，因此需要先启动后端。若改用后端完整地址，后端还需要提供相应的 CORS 配置；密钥和服务端 Token 不得放在 `VITE_` 环境变量中。

可在 `.env.local` 设置 `VITE_USE_MOCK_API=true` 使用 Mock，或设置为 `false` 使用真实 HTTP API。页面会明确显示 Mock 标识；真实请求失败时不会自动回退为 Mock 成功结果。Mock 仅保存在当前 JavaScript 运行环境中，不代表真实后端持久化。浏览器存储只记录不透明的 `application_id`，不保存病情自述。

- `src/api/`：统一 Fetch 请求、JSON 和错误处理。
- `src/components/layout/`：可复用页面布局和流程展示。
- `src/features/application/`：申请表单、集中校验和交互测试。
- `src/features/documents/`：文件校验、上传状态、文件列表及后端处理状态展示。
- `src/types/`：当前需要的契约类型。
- `src/mocks/`：从 `contracts/examples/application.example.json` 复制的虚构样例，仅供测试与后续开发。
- `src/styles/`：基础样式及 Tailwind 入口。

`pages/` 和 `hooks/` 将在出现独立路由页面或可复用自定义 Hook 时建立，避免空目录。

## 当前范围与接口

已完成基本信息、医疗情况、资金情况三步导航，及创建、更新和恢复申请的 API 调用。当前正式申请契约仅包含 `display_name`、`age_group`、`medical_summary`；资金字段、治疗时间和费用尚未定义，因此资金步骤只显示契约缺口，不收集或提交自创字段。

材料上传使用正式契约中的单文件 multipart 接口与幂等键；支持 JPEG、PNG、PDF，空文件在前端拒绝。契约未定义固定大小数值，因此前端不虚构平台上限，后端仍通过 413 和统一错误结构执行真实限制。Mock 仅在内存中保存文件元数据，不保存文件内容，页面完整刷新后允许丢失。

前端已包含 OCR/材料列表展示、Analysis 任务轮询、追问答案提交、Validation 问题展示、草稿生成与确认、JSON 申请包导出等客户端流程。真实成功与否仍依赖后端、Agent 和 Validation 的运行配置；导出响应没有有效 `download_url` 时，页面不会将其显示为可下载成功。

前端仅调用 FastAPI 的 `/api/v1` REST 接口，不直接调用 Dify 或其他模型服务。公共路径、请求与响应结构以仓库 `contracts/openapi.yaml` 和 `contracts/schemas/` 为准。业务 Mock 不参与生产页面逻辑，也不代表真实后端响应。

