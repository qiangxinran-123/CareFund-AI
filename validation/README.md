# D 模块：事实校验与证据溯源

最新进展与本轮结果请先读 `validation/CURRENT_STATUS.md`（2026-10-18）。`A_D_HANDOFF.md` 的首轮记录和旧验证目录保留历史上下文；当前回归入口包含最新 A 适配测试。

本模块接收 `contracts/schemas/validation.schema.json#/$defs/ValidationRequest`，返回同文件中的 `ValidationResult`。输入输出直接使用共享 Schema 校验，不另建一套 API 模型，不提供 FastAPI 路由，不修改申请、草稿或原始事实。

## 当前能力

- 校验结构、枚举、日期和金额。金额使用整数最小货币单位，拒绝负数、浮点数和布尔值。
- 追踪 `Fact -> Evidence -> UploadedDocument`；检查重复 ID、悬空引用、跨申请附件和未完成的附件解析。未知页码保留 `null`。
- 对同一 `field` 的不同取值报告冲突；金额包含币种比较，日期比较完整日期，不擅自选择某个来源或用户更正为真。
- 对材料事实执行保守的文本支持检查。输入中的 `supported` 不会跳过规则；无明确文本支持或带未处理否定、疑似语义的提取结果会被拦截。
- 根据显式业务配置检查必填字段、字段类型、材料来源及用户确认；`can_finalize` 只由是否存在 `blocking` 问题计算。
- 在确认及导出前重新核对当前事实、引用、申请/草稿版本和状态，检查草稿新增的常见金额、日期、数字及部分夸大表述。

校验结果只表示当前提交信息满足已实现的规则。OCR、用户确认、`supported` 和 `can_finalize` 均不代表材料真伪核实、医学诊断或平台审核通过。

## 安装和运行

从项目根目录运行，建议 Python 3.10 或更新版本。本次实际使用 Python 3.12。

Windows PowerShell：

```powershell
python -m venv validation/.venv
& ./validation/.venv/Scripts/python.exe -m pip install -r validation/requirements.txt
& ./validation/.venv/Scripts/python.exe -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -v
& ./validation/.venv/Scripts/python.exe -B -m validation validation/examples/request.demo.json --policy validation/examples/policy.demo.json
```

Linux/macOS 使用 `validation/.venv/bin/python` 替换上述虚拟环境解释器路径。

CLI 的标准输出为 JSON，退出码：`0` 表示规则允许完成，`1` 表示存在阻断问题，`2` 表示文件、配置或请求结构非法。错误信息不回显患者原文或被拒绝的敏感值。示例文件全部为合成数据，不能作为真实功能的固定输出；CLI 实际读取传入的 JSON 并执行规则。

## 与 B 的 Python 接入

只从后端调用，不从前端或 Dify 直接调用：

```python
from validation import (
    ContractValidationError,
    ValidationPolicy,
    validate,
    validate_for_confirmation,
    validate_for_export,
)

# 演示配置，仅供独立开发。正式的字段与材料清单需团队确认。
policy = ValidationPolicy(
    required_fields=("patient.medical_summary", "treatment.estimated_cost"),
    document_required_fields=("treatment.estimated_cost",),
    field_kinds={
        "patient.medical_summary": "text",
        "treatment.estimated_cost": "money",
        "treatment.recorded_date": "date",
    },
)

validation_result = validate(validation_request, policy=policy)

# application 和 draft 必须由 B 从当前存储读取，不能使用客户端提供的快照。
confirmation_result = validate_for_confirmation(
    validation_request, application, draft, confirmation_request, policy=policy,
)
export_result = validate_for_export(
    validation_request, application, draft, export_request, policy=policy,
)
```

三个入口都返回正式 `ValidationResult`，不新增响应字段。`confirmation_request` 使用正式 `DraftConfirmationRequest`，`export_request` 使用正式 `ExportRequest`，`application` 和 `draft` 分别为正式 `Application` 与 `Draft` 对象。

结构非法时抛出 `ContractValidationError`，B 应按 OpenAPI 转换为统一错误响应和相应 HTTP 状态；业务问题通过 `issues` 返回。D 不直接决定 HTTP 状态，不执行确认、状态转换、文件导出或数据库操作。

确认要求 Application 为 `draft_ready`、Draft 为 `generated`；导出要求 Application 为 `confirmed` 或 `exported`、Draft 为 `confirmed` 且存在有效确认时间。所有申请 ID、申请 revision、草稿 ID、草稿 revision 必须匹配。草稿使用的事实还必须已由用户确认。

B 必须将读取快照、调用检查、最终版本复查及状态/导出写入放在事务或等价并发控制中。D 的纯函数无法阻止检查完成之后发生的数据更新；本模块不替代后端的乐观锁和旧结果失效机制。

后端应保留 `issues` 和追溯信息并展示给用户；不能将 `can_finalize` 当作独立的、跨版本长期有效的审批凭证。

## 完整性规则配置

共享契约定义了事实结构，但尚未规定所有业务场景必填哪些字段、需要何种医疗材料。`examples/policy.demo.json` 使用已有契约示例中的字段演示配置，**并非已确认的生产材料清单**。

`ValidationPolicy` 是 D 模块内部配置，不是 API 请求字段：

| 配置 | 含义 |
| --- | --- |
| `required_fields` | 必须存在的事实字段，显式且不能为空 |
| `document_required_fields` | 必须具有材料来源的字段，是必填字段的子集 |
| `field_kinds` | 明确指定字段使用哪种 FactValue 类型 |
| `require_processed_document` | 是否至少需要一份已解析材料，默认 `true` |
| `require_user_confirmation` | 是否要求所有必填事实经过用户确认，默认 `true` |

未提供 policy 时仍执行通用校验，但返回 `validation.policy` 阻断问题，`can_finalize=false`。这样不会在必填规则未配置时误判完整。必填规则、字段类型和最终材料类别清单需要与 B/E 确认；涉及新增正式字段时仍必须先走契约变更流程。

用户自述或更正可以作为事实保留，并明确提示其来源；未经材料支持，不能仅凭 `user_confirmed=true` 标记为 `supported`。用户更正不会自动覆盖其他相矛盾的事实，须由 B 在用户澄清后维护当前事实集合并递增 revision。

## 规则边界和待联调内容

1. 材料支持检查是保守的字面核对。文本事实要求内容出现在引用文本中，并保留已识别的否定/不确定语义；无法确认的改写会提示补充或人工核查。一个事实引用多个证据时，每个引用均须支持该值，不支持用多个片段自动推理补全。
2. 金额支持检查识别常见阿拉伯数字、千分位、小数、万/亿和显式币种。当前实现 CNY、USD、EUR、GBP、JPY；人民币“元/￥/¥”和美元“$/US$”按这些常见记法解释，不适用于其他国家相同符号的自动判定。不执行汇率转换，不自动理解中文大写金额或任意 OCR 错字。
3. 日期支持检查识别完整年月日，不猜测缺失年份或模糊日期。整数和布尔值采用保守的直接匹配，不自动推断自然语言含义。
4. 草稿检查可发现已实现格式中的无依据金额/日期/数字，以及明确列出的部分风险短语。它不是完整的自然语言事实验证器，不能保证检测所有疾病、经历或困难程度的虚构、同义改写、否定翻转、中文数字或其他表达。B/A 必须继续落实受事实约束的生成、用户对完整草稿的人工确认及版本控制。
5. 已完成 A 交付源码边界与历史合成响应的本地离线适配，详情见 `validation/A_D_HANDOFF.md`。尚未接入在线 Agent、真实 OCR、后端事务或前端，也未验证端到端系统流程。材料真实性检查、材料类别识别和正式必需材料清单尚不在本地输入中，不能把“存在已解析附件”表述为全部材料已齐全。

## A / D 接口适配

适配入口为 `build_validation_request`、`prepare_agent_draft_request`、`validate_agent_draft`，调用方式和返回类型见 `validation/A_D_HANDOFF.md`。新材料事实为 `pending` 时 D 独立检查文本及引用，不自动改变事实状态。候选草稿按 A 当前逐事实格式校验；正式草稿的确认与导出仍由 B 调用原有入口并负责事务。

注意：A 当前拒绝任何非空问题 ID，D 则允许 info 来源提示与 `can_finalize=true` 同时存在。本次保留全部 ID，不绕过 A 门槛，需 A/B/D 确认后统一严重性规则。

## 测试与交付

测试位于 `validation/tests/`，覆盖正常输入、空集合、缺失/非法字段、金额与日期冲突、重复/悬空/跨申请引用、用户更正、不确定语义、伪造支持状态、草稿新增金额日期、旧 revision、确认状态、CLI 和输入不变性。每次结果还会校验输出 Schema，避免产生不符合正式契约的 issue 或结果。

本地工作分支：`feature/validation`。本地项目来自 ZIP，初始化后的 Git 仓库没有远程历史，也没有基线提交；原始文件会显示为未跟踪，不能据此将它们算作 D 的改动。本次开发内容全部位于 `validation/`。接回真实仓库后应核对远程基线，把本目录改动放到真实 `feature/validation` 分支，再按团队流程提交 PR；不要向真实仓库推送这个没有共同历史的本地分支。

PR 说明草案见 `validation/PR_DESCRIPTION.md`。
