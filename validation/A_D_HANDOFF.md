# D → A / B 接口适配交付

**当前版本说明（2026-10-18）：** 已继续适配 A 最新 ZIP（交付说明标注 `755a0c2`），新增字段范围、指令拦截、费用含义及完整文本匹配回归；最新 110 项测试结果与 API 说明见 `CURRENT_STATUS.md`。以下接口示例仍可用，涉及 `cc29e6d` 和 89 项测试的数字是首轮历史记录，不能作为最新版测试汇总。

本次按 A 交付包的提交 `cc29e6de047c49d20c79d628ed4dfa6a839c104c` 进行离线适配。共享契约与 D 本地的 V1 版本逐文件 SHA256 一致，没有修改 OpenAPI、Schema、契约示例或契约测试；A 源码也没有修改。改动全部位于 D 的 `validation/`，当前本地分支为 `feature/validation`，尚未提交或创建远程 PR。

## 已完成的接口

```python
from validation import (
    build_validation_request, validate, prepare_agent_draft_request,
    validate_agent_draft, validate_for_confirmation, validate_for_export,
)

# 以下都是 B 从当前存储维护的完整、同 revision 的快照。
# agent_service 是 A 的 AgentService；policy 是已明确配置的业务规则。
extract_response = agent_service.extract(extract_request)
validation_request = build_validation_request(extract_request, extract_response)
validation_result = validate(validation_request, policy=policy)

# B 单独保存/展示 extract_response 的 questions、warnings 及 validation_result。
# 用户确认或材料变化后，B 更新 revision，重新构造当前 ValidationRequest。
# 不要直接把未确认的原始候选当成已确认事实。
draft_request, draft_validation = prepare_agent_draft_request(current_validation_request, policy=policy)
if not draft_validation["can_finalize"] or draft_request["validation_issue_ids"]:
    # 暂停调用 A，返回待处理问题；不能删掉 IDs 强行通过。
    pass
else:
    candidate = agent_service.draft(draft_request)
    candidate_validation = validate_agent_draft(current_validation_request, candidate, policy=policy)
    if candidate_validation["can_finalize"]:
        # B 在事务中复查 revision 后，分配草稿/章节 ID 并保存正式 Draft。
        # 后续确认和导出仍分别调用 validate_for_confirmation/validate_for_export。
        pass
```

以上是接入顺序示例，不是已经实现的后端路由或数据库事务。D 不创建草稿 ID、不改变状态、不自动确认事实、不调用网络服务。

### 抽取映射

`build_validation_request(extract_request, extract_response)` 返回正式 `ValidationRequest`：

| D 输入字段 | 来源 |
| --- | --- |
| `schema_version`、`application_id`、`application_revision` | 请求和响应必须相同 |
| `documents` | 完整抽取请求的 `extracted_documents[*].document` |
| `evidence` | `extracted_documents[*].evidence` 展平 |
| `facts` | 响应的 `candidate_facts` 完整深拷贝，保留顺序及所有来源 |

适配器拒绝 ID 重复、跨申请附件、证据挂错附件、悬空证据、请求/响应版本不一致、遗漏或改写旧事实，以及新事实自行确认/标为支持。不按 `field` 去重，不推断用户自述真实性，不自动修正 ID、金额或页码。

只有 B 知道输入是否为完整快照；适配器不能发现调用方从请求和响应中同时省略的历史事实或附件。不能用它合并增量，也不能把第一次原始抽取响应与用户确认后的新 revision 混用。

### pending 与独立证据校验

A 的新事实按约定必须是 `pending`，且 `user_confirmed=false`。D 已修复原先“材料事实只要 pending 就直接阻断”的逻辑：现在直接核对当前证据引用和文本支持；能明确核对的 pending 事实不因这个状态本身被阻断。缺材料、文本不支持、金额不一致、未确认关键事实等问题仍会阻断；已标为 `conflicting/unsupported` 的事实也不会自动翻转。

D 不修改 `verification_status` 或 `user_confirmed`。D 的“当前规则通过”与材料验真不同。用户确认来源、确认操作记录与 revision 仍由 B 维护。

### 草稿内容适配

`validate_agent_draft(current_validation_request, agent_draft_response, policy=...)` 直接检查正式 `AgentDraftResponse`，返回正式 `ValidationResult`。不往 `ValidationRequest` 偷加 `draft/sections`，也不把候选章节伪装成已持久化的正式 Draft。

当前适配 A 的“一事实一章、完整原值、来源前缀、输入顺序”格式，检查时不调用 A 的生成函数。金额、预估/已付标签、来源、不确定限定词、引用、章节遗漏/额外内容或申请版本不一致都会阻断。此格式检查是 D 内部联调规则，不改变共享 Schema；A 后续更改固定文案格式时，需同步回归。正式草稿确认/导出检查也兼容该逐事实格式，包括非 CNY 的“最小货币单位”字面表示。

## 当前仍需 A / B / D 决定的门槛

**提示级问题与 A 草稿入口存在明确差异。** D 的 `can_finalize` 在没有 blocking 问题时可为 true；用户自述可伴随 info 来源提示。A 当前对任何非空 `validation_issue_ids` 都拒绝，包括 info。适配器保留全部问题 ID；B 应检查上面的两个条件并暂停。常见包含用户自述的流程因此仍可能被 A 阻断，这不是“全流程联调已完成”。

建议团队确认：保留完整问题记录，仅 blocking 控制生成；info/warning 持续展示。由于 A 草稿请求只含 ID，不含严重性，执行这一建议需要 A/B/D 共同约定 ID 的含义或按流程扩展接口，本次未单方面实施，也未删除问题或自动放宽规则。

其他待确认项：正式必填事实/材料与字段类型清单、合法同字段多记录、用户更正的替换与审计、D 问题如何进入 A 追问。`policy.a-handoff-demo.json` 仅作联调示例，**不是最终业务清单**；未配置 policy 时 D 禁止完成。

## 实际验证结果

- A 原版 62 项离线回归通过；其 7 份历史合成响应经过原版边界离线复验通过。这些不是新在线请求。
- D、契约与 A/D 适配回归共 89 项通过，含原有契约 10 项、原有 D 回归 54 项、适配回归 25 项。
- A 提供的四个抽取案例都能按原样映射；原始候选状态均未修改。在演示规则下四例均有待补充/确认问题，不能最终完成。第四例识别出 `inconsistent_amount`。
- 三份历史草稿符合当前字面格式，A 包没有随草稿输入提供完整材料/证据快照，因此 D 的补充检查不放行，未伪造证据来制造通过结果。
- 另用明确构造的纯合成、已确认材料事实 Mock 演示 A 草稿入口、D 候选检查、模拟 B 保存、确认、导出，以及 revision 增加后的阻断。确认标记只在该 Mock 测试中模拟，不来自真实用户操作。

生成的输入、D 结果和摘要见 `validation/verification/a_handoff/`。没有调用 Dify 或其他模型，没有使用真实患者 CSV，也没有端到端后端/前端、真实 OCR 或事务并发验证。

## 复现命令

在含 `contracts/`、`validation/` 的项目根目录执行：

```powershell
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r validation/requirements.txt
& ./.venv/Scripts/python.exe -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter -v
& ./.venv/Scripts/python.exe -B -m validation.tools.replay_a_handoff --output local-replay-results
```

测试中的 A 源码是交付包的原样子集，只作离线夹具，不安装到项目根 `agent/`。原始 SHA256 见 `validation/tests/fixtures/a_handoff/PROVENANCE.json`。D 运行时没有对 A 源码的 import 依赖。

## 收包与合并

交付 ZIP 包含完整 `validation/`、原样 `contracts/` 参考、实际测试/回放结果以及文件 SHA256 清单。安装到已有团队仓库时先核对契约，只引入 `validation/` 改动；不要覆盖 A 的 `agent/` 或用本包覆盖整个项目。`contracts/` 只是为了独立复现，不是契约更新。

收到后请 A/B 重点查看本页的“提示级问题与 A 草稿入口”决定项。接回真实仓库后，D 在真实 `feature/validation` 分支提交 PR，再按团队要求审查合并；当前 ZIP 副本无远程共同历史，不能直接推送为远程分支。
