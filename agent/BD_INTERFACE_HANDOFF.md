# A → B / D 接口交接与待确认清单

状态：本地提案，未向队友发送；不是团队决议或新的共享契约。

## 当前可接入的内容

正式输入输出仍以 `contracts/schemas/agent.schema.json` 为准。A 不定义 FastAPI 路由，不维护数据库版本、申请状态、确认状态或导出权限。

```python
from agent.agent_service import AgentService, AgentError
from agent.dify_runner import DifyRunner

service = AgentService(DifyRunner.from_env(user=authenticated_opaque_user_id))
candidate_analysis = service.extract(extract_request)
candidate_draft = service.draft(draft_request)
```

配置项：`DIFY_BASE_URL`、`DIFY_EXTRACT_API_KEY`、`DIFY_DRAFT_API_KEY`。两个操作使用独立 Dify 应用；只调用草稿时只需配置草稿密钥。适配器同步阻塞，异步后端应使用线程池。无自动重试、无 Mock 降级，默认超时 90 秒；超时后应先检查执行记录。`AgentError` 为可展示给开发者的脱敏原因，B 仍须映射成正式错误响应；不要返回 Python traceback、患者内容或密钥。

抽取已经用四个交接合成案例做过真实 API 联调；独立草稿于2026-10-16通过三个合成案例的真实调用。结果与限制见 DRAFT_IMPLEMENTATION_STATUS.md。交付 ZIP 的 verification/ 保存脱敏摘要和合成响应；本机原始报告保留于 agent/.local/。不能将离线测试或保存响应的离线复验当作新的在线调用。

v2另含MDCC补充评测摘要：23次抽取尝试、22份有效返回、3处审核加速措辞问题、37条未调用。当前模型额度200/200已用尽，在线联调阻塞；本地措辞候选尚未发布复测。62项Agent离线回归通过。完整待处理项见KNOWN_ISSUES.md；本包不附真实医疗摘录或其响应。

## 草稿首版的本地规则

由 `AgentService.validate_draft_request()` 在网络调用前检查：事实非空、ID 唯一、全部已确认、状态不能为 conflicting/unsupported、validation_issue_ids 为空；相同 field 的不同 value 暂时全部阻止，不能仅凭 pending 就放行。该规则可能阻止合法的多记录场景，是待团队确认的保守限制。

草稿采用一条事实对应一个章节，按输入顺序返回全部事实，每章只引用该 fact_id。内容保留完整原值、来源归属及不确定性。人民币只做分转元的确定性显示，不计算筹款目标或汇总总额。模型输出若增加病情、改金额、将预估写为已支付、删除限定词、伪称材料已核验、遗漏事实或额外扩写，A 会拒绝，不会自动修正文案或静默返回本地模拟结果。

这套固定排版是首版 A 模块策略，不改变 Schema，也不等于团队批准了最终文案风格。自由改写、合并章节和跨事实总结尚不支持。输入事实本身的正确性、材料支持情况及确认来源仍由 B/D 和用户保障。

## 需要 B/D 确认的事项

| 事项 | A 当前做法 | 提议及需确认的决定 |
|---|---|---|
| field 与必填 | 新抽取仍限开发测试字段；无明确规则则 required=false | B/D/E 确认业务字段表、必填依据；关系、已付费、材料补充字段仍为暂定，不把样例视为完整业务规则 |
| fact_id / question_id | 模型产生候选 ID；只保证当前请求内不重复 | B 决定全申请范围的 ID 权威与重试稳定性；重编号若被采用，必须同步维护全部引用，禁止修改已确认事实的旧 ID |
| 抽取输入完整性 | 必须传完整既有事实及其对应证据 | B 不能只传增量，也不能按 field 转为单值字典覆盖；A 强制完整保留旧事实 |
| 用户更正与替换 | 旧事实原样保留，修改产生新候选 | B/D 确认新旧事实的替换、失效和审计记录；当前契约没有 supersedes 等字段，不自行添加 |
| 多来源及多记录 | 抽取允许相同 field 的冲突候选；草稿遇到不同 value 阻止 | D 判断是否确有冲突；B 提供经过确认的当前有效事实快照。若同字段多条治疗记录合法，先确认对应表达规则后放宽草稿门槛 |
| 校验问题进入追问 | 抽取请求没有 validation_result 或问题详情字段 | 确认是否由 B 合成 user_input，或提契约变更；A 不按 issue ID 猜内容，不偷加字段 |
| 草稿门槛 | 所有 validation_issue_ids 都阻止；确认不代表证据真实 | B/D 确认严重性规则，不能只删除 ID 绕过。草稿请求无原始 evidence，D 必须在 B 编排中核对事实与当前证据 |
| 版本与导出 | A 校验返回 revision 与输入一致，只返回候选章节 | B 在保存事务中重查当前 revision；输入/附件变化时使旧草稿及确认失效。D 的确定性 can_finalize 和 B 的状态/版本检查共同约束确认导出 |

## B/D 集成验收建议

1. 未确认事实、已标记冲突、同字段不同值或未解决 issue 的草稿请求，在外部调用前被阻止。
2. 模型引用合法 fact_id 却新增费用或诊断，仍被 A 拒绝；D 对输入事实和证据做独立检查。
3. 模型执行期间用户修改申请，B 拒绝保存旧 revision 的结果。
4. 证据从申请中移除，B/D 重新校验并使相关旧结果失效。
5. 用户手工编辑草稿后重新执行语义、引用和最终状态检查；不能沿用生成时的通过结论。

需要调整共享契约或其他模块时，先由相关负责人确认；本文件不代替该确认，也没有触发提交、推送或通知。
