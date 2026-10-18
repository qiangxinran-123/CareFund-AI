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
