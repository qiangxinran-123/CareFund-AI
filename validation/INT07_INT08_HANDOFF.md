# INT-07 与 INT-08 规则及接入交付

本轮基于 `CareFund-AI-main (2).zip` 和联调分工落实 D 的任务，代码只修改 `validation/`，共享契约保持冻结。本页是 D 交付的演示规则与严重性映射，尚未取得 A/B 的人工确认，不冒充团队全链路已验收。

## demo_v1 的定位与加载

规则路径：`validation/policies/demo_v1.json`。名称：`demo_v1`。

**仅用于本次医疗众筹申请助手演示，不代表任何真实筹款平台的官方审批标准。**

必填要求沿用 B 现有 `backend/config/validation-policy.integration.json`：病情/检查情况说明、材料来源的后续费用预估，以及至少一份解析完成的材料。并未为了跑通而取消这些要求。尚未确诊时允许保留真实的检查进展和不确定性，不要求模型编造确定诊断。费用未知或无费用说明时应补充/澄清，在这套演示规则下不能最终放行。

B 可直接将现有配置改指向本文件，无须改公共接口或在后端复制一份规则：

```powershell
$env:CAREFUND_VALIDATION_MODE="real"
$env:CAREFUND_VALIDATION_POLICY="validation/policies/demo_v1.json"
```

B 现有 `RealValidationService` 调用 `ValidationPolicy.from_dict()` 即可加载，已在程序测试中执行。环境变量应使用项目根目录的相对路径或绝对路径。配置不存在/格式错误时启动报错；没有配置时 D 返回 `validation.policy` 阻断问题，不会暗中换成宽松规则。

D 独立使用：

```python
from validation import load_policy, validate
policy = load_policy("demo_v1")  # 也可传 JSON 的实际路径
result = validate(validation_request, policy=policy)
```

CLI：`python -B -m validation validation/examples/request.demo.json --policy demo_v1`。退出码 `0` 允许、`1` 有阻断、`2` 请求/配置非法。自带示例可能产生建议项 warning 或自述 info，这是正常结果。

## 严重程度判定表

| 条件 | 处理与严重性 | 允许生成/确认/导出 |
| --- | --- | --- |
| 缺少病情说明或其他可用检查说明 | `missing / blocking` | 否 |
| “尚未确诊/仍在检查”原文，保持来源及限定词 | 不猜测诊断，不因此额外阻断 | 满足其他规则时允许 |
| 缺少预估费用、所需材料来源或已解析材料 | `missing` 或 `unsupported / blocking` | 否 |
| 金额为负数、浮点/布尔或非法日期、枚举 | 结构拒绝 `ContractValidationError`；B 映射契约错误 | 否，不能产生假的通过结果 |
| 同一费用/日期字段存在不同值 | `inconsistent_amount` / `inconsistent_date / blocking` | 否，不自行选择某个来源 |
| 已付/预估含义混用，材料文本不支持 | `unsupported / blocking` | 否 |
| 无效证据/附件引用、跨申请、重复 ID | `unsupported` 或 `invalid_format / blocking` | 否 |
| 用户自述且未声称有材料支持 | `unsupported / info`，保留用户来源 | 满足其他规则时允许 |
| 仅自述的病情说明尚无材料来源 | 建议补充证据 `missing / warning`，不伪装为已证实 | 满足其他规则时允许 |
| 未填关系、城市或记录日期等演示建议项 | `missing / warning`，允许未知 | 满足其他规则时允许 |
| 任一传入草稿的事实未确认 | 分析检查必填事实；三个草稿门禁均 `missing / blocking` | 否，不自动替用户确认 |
| 含明显的编造、绕过规则等指令 | `unsupported / blocking` | 否，保留原文等待核实 |
| 申请/分析/草稿/请求 revision 或 ID 不一致 | `conflict / blocking` | 否 |
| 草稿未确认、缺确认时间，或已过期 | 状态/时间/版本阻断 | 不允许导出 |
| 草稿缺失事实、增加原文不支持的内容或改变来源 | demo_v1 按当前 A 逐事实格式严格核验，`unsupported / blocking` | 不允许确认/导出 |

`can_finalize` 只由当前确定性规则计算，任何 blocking 均为 false。结构非法直接拒绝，不将不合法金额或日期塞成“合法但通过”的业务结果。`ValidationRequest` 无申请姓名字段；生成及最终门禁额外接收正式 `Application`，检查显示名称不能为空白，其余表单必填仍由 B 的正式模型负责。

建议材料检查只根据当前提交快照中的事实来源判断，不识别/证明材料类别或真伪。其他材料清单后续若扩展，仍走团队确认和契约流程。

## 三个阶段的统一门禁

| 当前条件 | 生成草稿 | 最终确认 | 导出 |
| --- | --- | --- | --- |
| 无问题、所有输入事实已确认、快照当前有效 | 允许 | 正式草稿状态为 generated 时允许 | 正式草稿已确认且确认时间有效时允许 |
| 仅 info | 允许，完整提示保留 | 按相同事实与版本规则允许 | 按相同事实与版本规则允许 |
| 仅非阻断 warning，或 info + warning | 允许，完整提示保留 | 按相同事实与版本规则允许 | 按相同事实与版本规则允许 |
| 任一 blocking | 禁止 | 禁止 | 禁止 |
| revision 过期或无效引用 | 禁止 | 禁止 | 禁止 |

三个阶段不得把“用户点了确认”当作消除冲突或支持材料的证据。D 不修改任何原始事实/确认标记/申请状态，也不改变 B 的 revision。demo_v1 确认与导出采取 A 已实现的完整逐事实文字格式，不因为没有发现数字变化就放过新增的自由文本医疗经历。

## INT-08 的明确 ID 映射

冻结 Schema 只有 `AgentDraftRequest.validation_issue_ids`，没有严重性字段。demo_v1 的**内部显式配置** `draft_issue_scope=blocking` 约定：该草稿请求携带的是“当前尚未解决的阻断问题 ID”，不是“所有提示 ID”。对应完整 `ValidationResult.issues` 始终保留 info、warning、blocking，供前端展示及审计。

这不是删掉问题或强制传空列表。D 每次从当前完整快照重新执行规则：

- 有阻断：`can_finalize=false`，阻断 ID 全部保留；B 不调用 A。A 原有非空 ID 拦截仍能保护入口。
- 只有提示：`can_finalize=true`，请求中无阻断 ID，但配对的 D 结果含完整提示；A 的事实确认、冲突、指令和逐字输出检查仍照常执行。
- 旧配置的 `draft_issue_scope` 默认仍为 `all`，保留原有行为，避免未选择 demo_v1 的历史调用被静默改变。

这个映射不增删公共 JSON 字段，但属于需要 A/B 确认的跨模块使用约定。D 已给出实现和对真实 A 边界的离线验证；A/B 尚未人工确认，不能把本页当作已合并的团队决议。

## 给 B 的最小接入示例

```python
from backend.models import ValidationIssue, ValidationResult
from validation import prepare_agent_draft_request

# 以下对象必须从当前存储读取；policy 为已加载的 demo_v1。
# current_validation_request 包含完整 documents/evidence/facts，不能仅传增量。
prepared, checked = prepare_agent_draft_request(
    current_validation_request,
    policy=policy,
    application=application.model_dump(mode="json"),
    generation_request=payload.model_dump(mode="json"),  # 正式 DraftGenerationRequest
)
if not checked["can_finalize"]:
    # 按既有接口阻止生成，保留 checked 的完整问题返回/保存供前端读取。
    raise YourExistingValidationError()

full_validation = ValidationResult.model_validate(checked)
blocking_ids = set(prepared["validation_issue_ids"])
gate_issues = [ValidationIssue.model_validate(item)
               for item in checked["issues"] if item["issue_id"] in blocking_ids]

# 保留 full_validation.issues；只给 A 传正式约定的阻断问题。
# 使用 B 现有 RealAgentService，不直接调用 DifyRunner。
sections = agent_service.draft_sections(application, current_facts, gate_issues)
```

示例是调用位置说明，不是直接粘贴即包含事务的路由实现。B 还须保证 `current_facts` 与快照完全一致，并在模型完成后再次检查存储 revision，保存当前结果、完整提示和正式 Draft；其他 B 自身的阻断条件也必须保留。D 的 `validate_for_generation()` 可单独检查生成版本；`prepare_agent_draft_request()` 同时提供 application 和 generation_request 时会调用它。

确认和导出继续由 B 现有 `RealValidationService.validate_confirmation()` / `.validate_export()` 调用 D。当前 B 能加载新 JSON，也能调用这两个入口，无需 D 越界修改后端。

**尚未完成的 B 接入点：** 包中 B 的 `RealAgentService.draft_sections()` 仍把所有问题 ID 传给 A；只换 Policy 路径不能消除这个问题。测试已复现其对 info 的拒绝，再验证按上面映射调用相同 A 服务能够通过。B 需按本节接入，C 验收提示展示；本轮不替 B 修改源码。

## 已执行验证与限制

- 契约与 D 回归：129 项通过，含原有 110 项与新增 19 项 demo_v1 测试。
- D 内后端对接测试：5 项通过，包括 B 实际加载配置、确认/导出、错误映射、未配置拒绝及既有全 ID 转发差异。
- B 原有测试：11 项通过（其中原模块对接 3 项），API 测试采用 B 原有 Mock 模式，不能称为在线全链路成功。
- A 原有离线测试：108 项通过；测试中防覆盖用例的预期错误提示不代表失败，以最终 OK 为准。
- 六组合成门禁场景（无问题、info、warning、冲突、旧版本、无效引用）实际输入输出见 `verification/int07_int08/`。另有独立测试覆盖不存在 fact_id、未确认可选事实和缺少确认时间。

重跑：

```powershell
python -m pip install -r validation/requirements.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-results
# 若要运行真实 B 适配器及原有 B 测试，先装可选测试依赖：
python -m pip install -r validation/requirements-integration.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-backend-results --with-backend
```

没有调用模型 API、没有使用真实患者 CSV、没有启动真实前端/OCR/Dify 端到端流程。未承担 INT-01 至 INT-06 的 A/B/C 修复，也未接管需另行同意的上传幂等任务。本轮无人工 A/B 对接确认，无自动 commit/push/PR。
