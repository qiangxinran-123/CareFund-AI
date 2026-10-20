# A 最终联调交接（2026-10-20）

对应《联调修改.docx》中的 INT-02（A 对接）、INT-06、INT-07（A 对接）、INT-08。只修改 `agent/`；共享 contracts、B/D/C 源码未修改。文档提出的问题先与最新代码核对，已有功能不重复开发。

## A 本次修改

1. `AgentService.draft(request, validation_result=checked)` 可配对完整、同申请同版本的确定性 D 结果。info 和非阻断 warning 不再仅因 ID 列表非空就阻止草稿。blocking、`can_finalize=false`、ID 不匹配、重复 ID、无效关联事实仍在模型调用前拒绝。
2. 按 D 的 `demo_v1 / draft_issue_scope=blocking` 约定，发往 Dify 的请求只包含阻断问题 ID；完整 D 结果、原请求和全部提示保持不变。没有严重性上下文的旧调用继续保守处理非空 ID，不按 ID 名猜级别。
3. 增加安全的错误子类型，B 可以区分配置、网络/超时、HTTP、工作流失败和 Schema 错误，旧的 `except AgentError` 继续有效。异常中不附带服务端正文、患者正文或密钥。
4. 增加 `python -m agent.integration_smoke`：最多两次合成案例生成，经 B 的真实进程内适配器调用 A 和真实 Dify；自动核对两把应用密钥的角色，失败即停，无自动重试。

原有事实确认、证据引用、冲突、指令文本拦截、草稿逐事实逐字输出门槛保持有效；不改事实或自动替用户确认。正式 DSL 仍为 `workflow.deepseek-extract.yml` 和 `workflow.deepseek-draft.yml`，本次代码修复不要求手工改提示词或重新发布。

## B 的调用方式

导入路径和 JSON 仍使用既有契约：

```python
from agent.agent_service import AgentService, AgentError
from agent.dify_runner import DifyRunner

service = AgentService(DifyRunner.from_env(user=opaque_application_or_user_id))
analysis = service.extract(extract_request)  # AgentExtractRequest -> AgentExtractResponse
draft = service.draft(draft_request, validation_result=checked)
# AgentDraftRequest + 配对的 ValidationResult -> AgentDraftResponse
```

`validation_result` 是 **B 进程内的关键字参数**，不增加 `AgentDraftRequest` 的 JSON 字段，不来自前端或 LLM。`checked` 必须由 D 对当前存储快照确定性计算。A 校验其 Schema、申请、revision、问题 ID、关联事实以及阻断结论；A 不掌握 B 数据库中的当前版本，不能替代事务检查。

配对时 `draft_request.validation_issue_ids` 必须等于完整问题 ID 集合或 D 的完整 blocking 投影，任意遗漏/未知子集会拒绝。模型调用只发送 blocking 投影；完整问题不应从 AnalysisResult 或前端展示中删除。

返回结构：

- 抽取：`schema_version, application_id, application_revision, candidate_facts, questions, warnings`。
- 草稿：`schema_version, application_id, application_revision, candidate_sections, warnings`。
- 每项草稿章节为 `title, content, fact_ids`；正式 `section_id` 及 Draft 状态由 B 保存时生成。

### 沿用 B 现有 RealAgentService 的最小接入

截至核对的 main `26018f7`，B 的 `draft_sections(application, facts, issues)` 只接收问题列表，不能直接传上述关键字参数。可以直接使用 D 已提供的映射，保持 B 的适配器方法不变：

```python
from validation import load_policy, prepare_agent_draft_request
from backend.models import ValidationIssue, ValidationResult

prepared, checked = prepare_agent_draft_request(
    current_validation_request,
    policy=load_policy("demo_v1"),
    application=current_application.model_dump(mode="json"),
    generation_request=payload.model_dump(mode="json"),
)
full_validation = ValidationResult.model_validate(checked)  # 完整保存并展示所有提示
if not checked["can_finalize"]:
    raise ExistingBackendValidationError()  # 使用 B 既有错误处理
gate_ids = set(prepared["validation_issue_ids"])
gate_issues = [ValidationIssue.model_validate(item)
               for item in checked["issues"] if item["issue_id"] in gate_ids]
sections = real_agent_service.draft_sections(current_application, current_facts, gate_issues)
```

这是 **D 明确计算的阻断集合**，不是无条件传空列表。`current_facts` 必须与刚被 D 校验的完整快照一致；B 仍须保留自己的其他阻断条件。旧 B 直接把所有 info/warning ID 转发给 A、却不提供完整 D 结果时会继续拒绝，这是保留的安全边界。B 可采用本节映射，或扩展自身包装后调用 A 的完整结果关键字参数；不需要修改 A 内部规则。

### 同步、后台任务与版本

`extract()` 和 `draft()` 是同步阻塞调用。每次任务创建独立的 service/runner，避免共享 `last_*` 审计状态；默认 Dify 超时 90 秒，构造器可指定 `0 < timeout <= 300`。没有自动重试、Mock 降级或静默返回模拟成功。

异步后端在其受控后台任务中执行同步调用，例如 `result = await asyncio.to_thread(service.extract, request)`；不要在异步路由事件循环中直接等待完整生成后才返回 202。后台执行方式、queued/running/succeeded/failed、幂等和重启恢复均由 B 的任务层负责。

B 在调用前读取当前申请、全部事实、材料和证据，执行 D 的生成门禁；在模型完成后的保存事务中重查 revision。版本变化时丢弃旧结果并按既有错误返回。确认与导出仍调用 D 的对应门禁，不能把本次“允许生成”当成最终导出许可。

## 配置与错误约定

环境变量：`DIFY_BASE_URL`（默认 `https://api.dify.ai/v1`）、`DIFY_EXTRACT_API_KEY`、`DIFY_DRAFT_API_KEY`。密钥分别对应两个独立、已发布的 Workflow 应用；DeepSeek 供应商密钥配置在 Dify 内，不作为这两个变量的值。密钥仅在本地环境或临时隐藏输入中配置，不能入库或写普通日志。

所有异常继承 `AgentError`（也可继续从 `agent.agent_service` 导入）。具体子类型在 `agent.errors`：

| 情况 | 类型 / code | B 处理 |
|---|---|---|
| 地址或应用密钥未配置 | AgentConfigurationError / agent_configuration_error | 任务安全失败，提示检查配置 |
| 断网、连接中断、超时 | AgentTransportError / agent_transport_error | 任务失败；execution_may_be_running=true，不立即重复生成 |
| HTTP 非成功 | AgentHTTPError / agent_http_error | 保留安全的 status_code 和 allowlist provider_code；不输出响应正文 |
| Workflow 未成功 | AgentWorkflowError / agent_workflow_error | 任务失败，不返回候选成功结果 |
| JSON/Schema 非法 | AgentContractError / agent_contract_error | 拒绝结果，不保存为成功 |
| 事实、引用、版本或门禁拒绝 | AgentError / agent_rejected | 按正式业务错误处理，保留完整 D 问题 |

B 现有 AgentIntegrationError 包装仍可使用，其受控 `__cause__` 保留 A 子类型；不要向前端发送 traceback。未知 runner 异常仅报安全的 `Agent runner failed`，不序列化任意异常正文。

## 已执行的离线验证

- A 132 项、共享契约 10 项测试通过。
- A/B/D 专项 9 项通过，含六种 D 门禁场景：无问题、info、warning、费用冲突、旧版本、无效 evidence 引用；另覆盖无效 fact 引用、未确认事实、B 错误传播、独立后台线程，以及两次调用上限与失败即停。
- B 原有 11 项测试通过，使用其原测试替身，不能视为在线全链路成功。
- D 119 项测试通过的前提及原始问题见下一节；不是对 GitHub 原样目录“直接全绿”的声明。
- 87 份既有保存响应再次离线回归：81 份抽取事实不变、5 份正常草稿通过、1 份指令草稿按预期拦截；历史响应未改写。

证据保存在 `verification/integration-final-20261020/`。本轮另有 2 次合成真实生成通过：抽取 3.952 秒、草稿 4.117 秒，均经 B 进程内适配器 → A → 真实 Dify；离线替身结果不计入这 2 次成功。复验命令：

```powershell
python -m unittest discover -s agent/tests
python -m unittest discover -s contracts/tests
python agent/verification/integration-final-20261020/verify_peers.py --team-root <正确布局且包含最新B和D的项目根目录>
python -m agent.integration_smoke --gui --backend-root <上述项目根目录>
```

真实复测只用人工合成关系、费用材料和已确认事实，最多 2 次生成；不启动前端、实际 OCR 或 HTTP /analyze，不冒充完整端到端、持久化或最终导出验收。

本轮真实运行证据为 `live-results.json`：北京时间 2026-10-20 21:21 完成，两把应用密钥经只读应用名查询分别核对，恰好 2 次生成，0 次重试；当前 A/B 源码指纹与记录一致。抽取只返回关系和材料预估费用，证据 ev_demo_001 有效，没有生成新病情、已付费用或日期；草稿全部 4 条事实及“尚未确诊”原文逐字保留。D 的 3 条 info、3 条 warning 全部保存在配对结果，未因生成成功被删除。`live-status.json` 保留输入前 0 次调用的历史快照，当前状态以 live-results 为准。

这里只注入内存凭据工厂，B/A 的实际方法及 HTTP 传输均未 Mock；D 最终包使用前述规范化隔离目录。密钥未持久化；不是对未整理的 GitHub 原始目录或整个网页闭环的通过声明。本次修改尚未提交/推送，提供的是可核验的本地代码和交付包。

## 已发现的对接事项（由对应成员处理）

1. **B 接入映射**：其当前所有 ID 转发会把 info 一起交给旧式 A 调用。本节已给出经程序验证的最小接入方法，B 在自己目录落实并保留全部提示。
2. **D 最终目录**：main `26018f7` 将新 demo_v1 放在 `validation/validation/`，外层 `validation/` 还是旧版；直接 `from validation import load_policy` 和 `validation/policies/demo_v1.json` 不会命中最终版。D 应整理自己的交付目录，B 再加载。A 只在忽略的隔离副本中把内层最终包放到预期根目录测试，没有替 D 改 Git 源码。
3. **D 历史夹具换行**：Git 中 20 个夹具文件为 CRLF，但既有来源清单记录原 LF 字节，原样运行会触发 13 个指纹子检查失败及 1 个回放错误。隔离测试仅在 CRLF→LF 后精确匹配原清单的 size 和 SHA-256 时恢复原字节，不改清单，随后 119 项通过。D 需要在其分支处理打包/换行问题。

以上未修改其他成员模块，也没有将其工作标作 A 已完成。E/C 的真实页面、B 的异步状态和事务、D 的正常目录确认应在小组验收时补齐记录。
