# CareFund-AI 前端

第一阶段前端工程骨架。技术栈：React、Vite、TypeScript（strict）、Tailwind CSS、原生 Fetch API、Vitest 和 React Testing Library。

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

- `src/api/`：统一 Fetch 请求、JSON 和错误处理。
- `src/components/layout/`：可复用页面布局和流程展示。
- `src/types/`：当前需要的契约类型。
- `src/mocks/`：从 `contracts/examples/application.example.json` 复制的虚构样例，仅供测试与后续开发。
- `src/styles/`：基础样式及 Tailwind 入口。

`pages/` 和 `hooks/` 将在出现实际页面或自定义 Hook 时建立，避免空目录。

## 当前范围与接口

已完成应用基础布局、请求层、契约错误类型、一个申请响应样例和基础测试。申请表单、真实上传、AI 分析、追问、草稿确认和导出均未实现；页面不会自动请求后端。

前端后续仅调用 FastAPI 的 `/api/v1` REST 接口。公共路径、请求与响应结构以仓库 `contracts/openapi.yaml` 和 `contracts/schemas/` 为准。业务 Mock 不参与生产页面逻辑，也不代表真实后端响应。

