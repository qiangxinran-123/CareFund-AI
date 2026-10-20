
# D 模块当前联调交付状态

更新日期：2026-10-20（Asia/Shanghai）。基于 `CareFund-AI-main (2).zip` 和最终联调任务说明，只修改 `validation/`，工作分支为本地 `feature/validation`，未提交/推送/创建 PR。

## 本轮已完成

- INT-07：提供命名演示规则 `validation/policies/demo_v1.json`。沿用 B 原 integration policy 的病情说明、材料支持的后续费用预估、已解析附件和事实确认要求；不擅自取消必填内容。对关系、城市、日期和病情自述的材料来源设置非阻断建议。未确诊时允许保留检查进展和不确定性。
- INT-08 的 D 侧：显式约定 `draft_issue_scope=blocking`，A 草稿请求只接收阻断 ID，完整 `ValidationResult.issues` 保留所有提示供前端和审计使用；旧配置默认仍保留 all-ID 行为。
- 新增 `validate_for_generation()` 检查当前申请及生成请求版本，生成、确认和导出均核对事实确认、冲突和引用；demo_v1 最终草稿按 A 当前逐事实格式严格核验，不以数字没变为由放过新编写的医疗经历。

规则仅适用于本次演示，不代表平台官方审批标准。严重性表、门禁表及 B 最小接入示例见 `INT07_INT08_HANDOFF.md`。

## 实际测试

| 范围 | 结果 |
| --- | --- |
| 契约与 D 回归 | 129 项通过（原 110 + 新增 19） |
| D 的真实 B 适配器测试 | 5 项通过 |
| B 原有测试 | 11 项通过，API 场景为原有 Mock 模式 |
| A 原有离线测试 | 108 项通过 |
| 六组合成门禁案例 | 正常、info、warning 允许；冲突、旧版本、无效引用阻断 |
| 模型 API 新调用 | 0 次 |

日志和实际输入输出位于 `verification/int07_int08/`。A 的测试最初受沙箱临时目录权限阻止，放开该限制后 108 项通过。B API 测试在导入时配置 Mock 单例，验证脚本将其与 D 真实适配器测试分进程运行，避免导入顺序共享 Real 单例。

```powershell
python -m pip install -r validation/requirements.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-results
# 可选后端适配回归：
python -m pip install -r validation/requirements-integration.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-backend-results --with-backend
```

## 对接方仍需完成

1. A/B 确认阻断 ID 与完整提示列表的约定；尚未取得人工确认，不冒充团队决议。
2. B 加载 demo_v1 并接入 D 的生成映射。B 当前全 ID 转发仍会让 A 拒绝 info，测试已复现；只更改配置路径还不能完成系统修复。
3. B/C/E 验证事务、持久化、用户确认操作、在线 OCR/Dify、提示展示和最终下载。

未修改 A/B/C 或公共契约，没有承担上传幂等、数据库或其他成员任务。旧的 10 月 16/18 日记录只作为历史证据保留，当前规则以本页及 INT07_INT08_HANDOFF 为准。
=======
# D 模块当前交付状态

更新日期：2026-10-18（Asia/Shanghai）。本轮根据 `CareFund-AI-main (1).zip` 中 A 的实现继续本地开发，工作分支为 `feature/validation`。A 的 `CURRENT_HANDOFF.md` 标注功能提交为 `755a0c2`，ZIP 不含 Git 历史，本次以 ZIP SHA256 和实际源码指纹定位版本。

## 本轮已经完成

1. 核对新版包中的 13 份正式契约文件，全部与 D 本地逐字节一致。没有修改契约、A 源码或其他成员模块。
2. D 抽取适配器对齐 A 当前字段范围：只允许现有六类新候选字段及对应追问范围；原有历史事实仍完整保留，不因字段范围检查被删除。
3. 增加独立、有限的指令检查。事实中出现“忽略规则”“编造费用”等明显生成指令时，即使已确认、原文有引用或符合 A 的逐事实文案格式，D 在事实、候选草稿、确认和导出阶段仍返回阻断问题。不会删除原文、改状态或自动调模型。明确的“不要编造费用”等否定表达不会按本规则视为执行指令。
4. 增强材料费用语义检查：金额相同不足以证明费用字段成立。`treatment.paid_cost` 需要同一分句中明确已付含义；`treatment.estimated_cost` 需要明确预估含义。反向引用、金额未标明含义、否定付款或跨句借用标签时均提示核实。两个字段本来就代表不同含义，数值不同不会直接作为同字段冲突。
5. 修复完整原文含句号/多句时的文本匹配误拦：与证据全文完全一致的事实保留标点、否定和不确定性。删掉“疑似/尚未确诊”等限定词的改写仍不能通过。

这些检查均是确定性、保守的本地规则，不是完整的医疗语义理解或材料验真。费用措辞尚不能覆盖所有医院票据、中文大写金额、OCR 错字或其他语言；模糊情况会要求核实，不猜测付款状态。

## 实际验证

| 本次实际执行 | 结果 |
| --- | --- |
| 最新 A 原版离线单元测试 | 108 项通过 |
| A 自带公开保存响应复验 | 21 个抽取事实不变、5 个正常草稿通过、1 个指令草稿在调用前拦截 |
| D + 统一契约 + 历史与最新适配测试 | 110 项通过，其中统一契约 10 项、D/适配 100 项 |
| 最新 A → D 公开合成案例回放 | 27 例全部返回符合契约、引用及版本检查的 D 结果，输入不变；指令案例由 D 独立阻断 |
| 新增在线 API 调用 | 0 次 |

复现命令（项目根目录）：

```powershell
python -m venv .venv
& ./.venv/Scripts/python.exe -m pip install -r validation/requirements.txt
& ./.venv/Scripts/python.exe -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -v
& ./.venv/Scripts/python.exe -B -m validation.tools.replay_latest_a --output local-replay-results
```

`validation/verification/a_20261018/` 保存此次实际 D 输入、结果和摘要；`tests/fixtures/a_20261018/PROVENANCE.json` 记录公开合成夹具与 A 源码的原始指纹。旧 `a_handoff/` 目录保留 10 月 16 日的历史结果，不表示本次重新在线执行。

27 例在演示 policy 下全部 `can_finalize=false`：抽取结果仍是候选，可能缺材料、关键字段或用户确认；A 草稿输入不含原始附件和证据，不能伪造缺失的材料来制造最终通过。草稿字面格式兼容与最终允许确认导出分别验证，不能混为一项成功率。

A 的交付材料报告历史批次共 1,350 次真实调用、1,341 份可解析保存响应；私有原始响应和账本未随包提供。本轮没有独立复现这批数据，不能把这些数字当作 D 的测试量、临床准确率或全数据集验收结果。

## 接口和当前阻塞项

调用入口沿用：

- `build_validation_request(extract_request, extract_response)`：完整同版本抽取快照无损映射。
- `validate(request, policy=...)`：正式 `ValidationRequest -> ValidationResult`。
- `prepare_agent_draft_request(request, policy=...)`：同时返回正式 A 草稿请求与当前 D 校验结果，保留全部问题 ID。
- `validate_agent_draft(request, candidate, policy=...)`：独立检查正式候选草稿响应。
- `validate_for_confirmation(...)` / `validate_for_export(...)`：对 B 当前存储快照重查版本、状态、引用和规则。

完整调用示例见 `A_D_HANDOFF.md`。所有入口保持原事实和状态；运行时不依赖 `agent/`。B 必须通过最新 `AgentService` 调用 A，让 A 的展示和输入策略生效；不能直接调 Dify 并把原始输出当作已处理结果。

仍需共同确定：

1. **严重性映射**：A 最新版仍拒绝任何非空 `validation_issue_ids`，D 的 info 提示可能与 `can_finalize=true` 同时存在。本轮仍完整保留 IDs，未单方面改变 A 或契约；B 需同时检查 D 是否允许、A 请求是否含问题 ID。常见自述流程因此仍可能暂停，不应报告全链路已完成。
2. **正式必填和材料规则**：现有 policy 是演示配置，正式清单须由团队确认；未配置规则时禁止最终完成。
3. **B 的有效快照和事务**：用户更正、事实确认、附件变化必须由 B 维护 revision 和旧结果失效。D 不创建数据库状态，也无法独立验证真实用户确认来源或消除事务竞争。

## 是否需要 API

**D 自身不需要额外模型 API。** 当前开发、规则检查和保存响应回放都在本地完成，不依赖模型密钥。

等 B 具备后端入口，要验证“新输入 → A 在线抽取/生成 → D 校验”的真实链路时，需要由 A/B 在后端环境配置：

- `DIFY_BASE_URL`：A 已部署的服务地址；
- `DIFY_EXTRACT_API_KEY`：抽取应用密钥；
- `DIFY_DRAFT_API_KEY`：草稿应用密钥；
- Dify 内已经配置好可用模型供应商和额度。

通常不需要 D 再拿一份 DeepSeek 供应商密钥；模型供应商由 Dify 管理。密钥通过本机环境变量或团队安全渠道配置，不放进代码、报告、压缩包或聊天记录。当前包尚无 B 的实现，因此本轮不请求凭据、不运行付费在线批次。

代码仍只在本地，未自动 commit、push 或创建 PR。接回真实仓库时将 `validation/` 改动放入真实 `feature/validation` 分支，再提 PR 审查。

