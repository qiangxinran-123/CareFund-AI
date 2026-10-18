# 独立草稿工作流导入与真实验证

2026-10-16 补充：线上两个应用已改用 DeepSeek V4.1 Flash，7 次合成编辑器运行及 2 次 Service API 冒烟复测通过，最新导出已核对并同步。当前草稿文件为 [workflow.deepseek-draft.yml](workflow.deepseek-draft.yml)，配置见 [DEEPSEEK_SETUP.md](DEEPSEEK_SETUP.md)。以下为原 GPT 版本的导入及历史验证说明，不能重新导入后直接视为 DeepSeek 配置。

导入文件是 `agent/workflow.draft.yml`，应用名为 **CareFund-已确认事实草稿-首版**。它沿用已成功抽取应用导出的 DSL 0.7.0、gpt-4.1 和 OpenAI 插件标识，不包含任何密钥。新文件是 JSON 形式的 YAML；Dify 的导入器使用 YAML 解析器读取。参考：[Dify 官方导入实现](https://github.com/langgenius/dify/blob/main/api/services/app_dsl_service.py)。当前用户实例已完成导入、发布及三个合成草稿案例的真实调用（2026-10-16），详见 DRAFT_IMPLEMENTATION_STATUS.md；其他实例仍须核对依赖和模型配置。

## 在 Dify 中的操作

1. 进入工作室，从工作室入口选择“导入 DSL 文件”，选择 `workflow.draft.yml`，**创建新的草稿应用**。现有信息抽取应用继续保留；不要在旧应用内覆盖导入。
2. 导入后应有三个节点：已确认事实输入 → 事实逐条成稿 → 候选章节输出。开始变量为 `request_json`，结束变量为字符串 `result`。
3. 检查 LLM 节点：使用已经可用的模型供应商配置，默认沿用 gpt-4.1、temperature=0。不需要重新购买模型密钥。如提示插件或 DSL 版本不兼容，保留现有抽取应用，把不含密钥的错误信息交给 Codex 处理。
4. 发布这个独立草稿工作流。在该草稿应用的 API 访问页面创建草稿应用 API 密钥，保存在本地；不发到聊天，不使用原抽取应用密钥。应用执行 API 不能代替控制台创建/发布工作流。
5. 完成后告诉 Codex“草稿已发布”，由 Codex 打开本地隐藏密钥窗口并执行三条合成请求；或在项目根目录自行运行：

```powershell
.\.venv\Scripts\python.exe -m agent.draft_live_check --gui
```

三个请求覆盖：已确认事实与两类金额；未确诊与小数金额/未知费用；事实文本夹带编造指令。最后一项要求把原文本作为引文保留，不执行其中指令、不添加事实。它不是对任意提示注入的全面证明。

结果保存在 `agent/.local/draft-live-status.json` 和对应时间戳目录。失败即停、不重试。只有状态为 `three_synthetic_draft_calls_passed` 才表示这三次真实返回均通过 Schema、身份版本、引用与固定排版内容检查。仍需要核对 Dify 运行记录，并由 B/D 在真实编排中保障输入事实、证据及最终导出。

单条请求入口：

```powershell
.\.venv\Scripts\python.exe -m agent.run_draft agent/examples/draft-request.json --user opaque_demo_user
```

支持环境注入 `DIFY_DRAFT_API_KEY`，不会自动加载 `.env`。前置条件失败会在索取密钥及联网之前退出。

## 抽取措辞修复

本地候选 `agent/workflow.extract-v2.yml` 新增措辞规则：没有输入支持时，不代替平台发出建议、要求或审批条件，也不声称补充材料能加快审核或提高通过率。可读提示词在 `agent/prompts/extract-v2.md`。原始 `workflow.yml` 和 `prompts/extract.md` 留作已验证版本；MDCC首轮发现的3处措辞问题尚未验证线上修复。

这是待应用/发布的本地修订，还没有新的真实响应。可以在原抽取应用中仅追加该条规则，经检查后发布并重跑案例 02；也可从工作室导入为另一个测试应用。不要把本地文件更新误称为线上问题已修复。

## 本地再生成文件

修改草稿提示词后运行下面的命令生成新的导入候选；它不会发布到 Dify：

```powershell
.\.venv\Scripts\python.exe -m agent.build_workflows
```
