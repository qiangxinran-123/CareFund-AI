# A 第二次联调修改与交接

本次按《联调修改第二次.docx》的 A 任务实施，基线为 main `b9c1f668b561a27fd8d9a45340ce1353473d0c0e`。只修改 agent 目录。代码及离线验证已完成。本轮经用户授权的两把应用密钥核对后，A 独立模式的真实抽取、草稿生成各一次均通过，新增真实模型调用为 2，自动重试为 0。密钥未写入仓库或报告。

## 已修复问题

1. 原联调脚本先按 D 规则筛选问题，再调用 B。这能验证一种建议接法，但不能证明 B 当前 HTTP 路径有效。现在默认 backend 模式传递完整问题列表，不再替 B 转换。新增 agent 模式，直接验证 A 接收完整同版本 D 结果的正式入口。报告明确标记模式。
2. 新增 non-interactive 参数；缺少任意一把环境密钥时明确失败，不等待隐藏输入、不产生 API 调用。
3. 运行配置提前检查 URL 端口、空白字符、密钥类型及空白字符、超时类型。错误统一为安全的 AgentConfigurationError，不泄露配置值。只配置一个工作流的既有调用仍支持，空环境变量视为未配置。
4. 调用次数在实际进入模型传输前记录。A 门禁在本地拒绝不再算一次模型调用；每次执行最多两次生成，失败不重试。业务操作次数另记 operations_attempted。
5. 新增错误配置和验收模式回归，更新当前交接入口。旧线上成功记录保留原样，不作为本轮验收结果。

## 工作流与环境配置

| 配置 | 值或来源 |
| --- | --- |
| DIFY_BASE_URL | 默认 https://api.dify.ai/v1 |
| DIFY_EXTRACT_API_KEY | 已发布的 CareFund-信息抽取与追问-修订版的应用 API Key |
| DIFY_DRAFT_API_KEY | 已发布的 CareFund-已确认事实草稿-首版的另一把应用 API Key |
| 抽取正式 DSL | agent/workflow.deepseek-extract.yml |
| 草稿正式 DSL | agent/workflow.deepseek-draft.yml |

本地 DSL 均保留 request_json 输入和 result 输出，未发现需要为本轮改动重新发布的接口变化。本轮已通过 /info 核对两个线上应用名称及模式，并完成真实生成。应用若被改名需核实映射，不能猜测密钥角色。供应商密钥配置在 Dify 内，不填入上述应用密钥变量。

backend/.env.example 只是示例，DifyRunner 不自动加载 .env 文件。B 应把变量设置到启动 FastAPI 的同一进程环境，或者明确使用 uvicorn 的 --env-file 加载本机未入库的配置文件。两把应用密钥不要发到聊天、写入提交或命令历史。

## A 真实验收

在完整仓库根目录安装 backend/requirements.txt 中的依赖；当前工具会使用 B 的数据模型及 D 的 demo_v1 校验。无需启动 HTTP 服务。

本机隐藏输入密钥，执行 A 独立验收：

```powershell
python -m agent.integration_smoke --mode agent --gui
```

已经安全配置环境变量时：

```powershell
python -m agent.integration_smoke --mode agent --non-interactive
```

每次仅使用内置虚构材料，抽取一次、草稿一次；核对 Schema、申请版本、证据引用、金额、候选未自动确认，以及四条已确认事实的逐字草稿。记录在 agent/.local 的独立时间目录，失败不覆盖之前结果。成功需退出码 0、mode=agent、status=two_real_calls_passed、calls_attempted=2，并检查两项 cases；这仅证明 A 的本轮真实验收。

GUI 输入的凭据只供当前进程使用，不会自动配置 B 的服务进程。

## B 必须落实的对接事项

最新 B 的 draft_sections 仍将全部 issue ID 传给 A，未传完整 ValidationResult；即使 D 只返回 info 或 warning 且 can_finalize=true，A 也会因缺少严重性上下文而拒绝。当前集成测试明确复现这一缺口。不能靠删掉所有问题或放宽 A 门禁解决。

B 推荐扩展内部适配器：在路由锁内获取完整校验结果与事实的同版本深拷贝，并把完整结果作为进程内上下文转交 A：

```python
result = service.draft(request, validation_result=checked.model_dump(mode="json"))
```

checked 必须是 D 对当前可信快照产生的 ValidationResult；request 中的问题 ID 使用其完整集合，事实与版本必须对应。完整提示继续保存和展示；A 仅将 blocking ID 送往模型。模型返回后 B 仍应重查 revision。也可采用 FINAL_INTEGRATION_HANDOFF.md 所述 D 显式映射，但须在 B 的实际执行路径实现。

B 修改后再运行：

```powershell
python -m agent.integration_smoke --mode backend --non-interactive
```

当前脚本调用的是现有三参数 B 适配器。若 B 扩展为需要完整结果的新接口，应同步调整脚本以传真实完整上下文；不得在脚本中代替生产路径做筛选。backend 模式也只是进程内适配器检查，不等于 HTTP、OCR、浏览器、持久化与最终下载的完整验收。C/E 按任务书完成网页闭环。

## 当前状态

本轮离线结果与真实验收汇总见 verification/second-integration-20261021/summary.json，新真实响应见同目录 live-results.json。抽取耗时 8.568 秒，草稿 7.639 秒；候选未自动确认、引用有效，四条已确认事实及“尚未确诊”原文逐字保留。首次缺少凭据的检查保留为历史记录，当前真实验收已通过。2026-10-20 的线上成功仍为独立历史证据，没有改写。D 导入问题及 B 下载功能在当前 main 已更新，不再列为 A 待修问题。本轮交付分支为 fix/agent-second-integration，目标为 main；是否合并以 GitHub PR 状态为准。
