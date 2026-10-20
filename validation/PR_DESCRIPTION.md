
# fix: finalize demo validation policy and draft severity gates

落实 INT-07 与 INT-08 的 D 侧：提供 demo_v1 和明确的严重性/阻断 ID 映射，info/warning 保留展示且不单独阻止草稿；冲突、无效引用、未确认事实与过期版本继续阻断。

只修改 `validation/`。新增命名 Policy 加载、建议项 warning、生成前当前版本检查，以及与确认/导出一致的事实门禁；demo_v1 最终草稿要求完整保留 A 当前逐事实原值和来源。旧配置默认保留全 ID 行为，不静默改变历史调用。A/B/C 和公共契约均未修改。

## 验证

```powershell
python -B -m validation.tools.verify_int07_int08 --output local-int-results --with-backend
python -B -m unittest discover -s agent/tests -q
```

契约/D 129 项、D 后端适配 5 项、B 原有 11 项、A 原有 108 项测试通过。六组门禁案例覆盖正常、info、warning、金额冲突、旧 revision 和无效引用；另有不存在 fact_id、确认时间、未确认可选事实及自由文案篡改回归。只用合成输入与离线 runner，模型调用 0 次。

详细规则和接入示例见 `INT07_INT08_HANDOFF.md`，实际日志见 `verification/int07_int08/`。A/B 需确认草稿请求只传阻断 ID 的约定；B 将 Policy 路径改为 `validation/policies/demo_v1.json`，并接入 D 映射、保留完整提示给前端。

B 原有全 ID 转发仍会误阻断 info，测试明确记录该现象；本 PR 没有越界修改 B。尚未完成人工 A/B 确认及在线系统/事务验收，不宣称全链路问题已关闭。
=======
# feat: implement fact validation and adapt Agent handoff contracts

## 实现内容

实现 D 模块的 `ValidationRequest -> ValidationResult` 独立校验流程，包括证据引用、跨申请/重复标识、材料解析状态、事实冲突、可配置完整性规则，以及草稿确认/导出前的引用、状态和版本检查。对部分无依据的草稿金额、日期、数字及夸大表述增加阻断检查。

适配 A 最新交付（说明标注提交 `755a0c2`）：无损转换完整抽取快照，对齐新候选字段范围，重新校验草稿前置条件并保留全部问题 ID，支持直接核验 A 的逐事实候选章节。材料 pending 候选由 D 独立核对，不再只因该状态阻断，也不自动改写状态或确认标记。新增明显生成指令阻断、已付/预估费用含义核对，以及标点和不确定性原文保留回归。

只修改 `validation/`。公共 OpenAPI、Schema、示例、契约测试及其他成员目录均保持原样。运行时直接加载 `contracts/schemas/`，不复制模型，不新增服务框架，不调用外部模型。依赖限定为 JSON Schema 校验及其本地引用解析组件。

## 验证

在 Python 3.12 独立虚拟环境中运行：

```powershell
& ./validation/.venv/Scripts/python.exe -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -v
& ./validation/.venv/Scripts/python.exe -B -m validation validation/examples/request.demo.json --policy validation/examples/policy.demo.json
```

已通过 110 项测试：10 项契约测试、100 项 D 与适配回归。另在最新 A 原样交付快照中通过其 108 项离线回归，公开 27 例保存响应按新版 A 和 D 实际实现复验；21 个抽取事实不变、5 个草稿格式兼容、1 个指令草稿由双方独立拦截。无新在线模型调用。历史 1,350 次调用与私有批次未在 D 本轮重现，未作为 D 验收量。

## 需审查和后续联调

- 与 B/E 确认正式必填事实、字段类型和材料清单；现有 policy 明确仅为演示配置。不传配置时禁止最终确认。
- A 当前阻断所有非空 validation_issue_ids，包括 D 的 info 问题；本次未删 ID 绕过，需 A/B/D 统一严重性门槛。详细交接说明和实际四例回放结果见 `validation/A_D_HANDOFF.md` 及 `validation/verification/a_handoff/`。
- B 使用当前存储快照接入三个函数，并保证事务/并发控制、状态转换与旧结果失效。
- 文本和草稿检查是保守的规则校验，不能证明医学语义或材料真实性；自由文本仍须受事实约束生成并人工确认。
- 尚未进行真实 OCR、Agent、后端与前端的端到端联调。

本文件是供本地工作后使用的 PR 说明草案，尚未创建远程 PR。本地 ZIP 副本没有远程共同历史，需先将 `validation/` 改动移入真实仓库的 `feature/validation` 分支。

