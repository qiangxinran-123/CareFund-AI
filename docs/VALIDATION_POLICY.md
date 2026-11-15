# CareFund V1 正式业务 Policy

状态：已冻结，用于 AI WEB 网页开发挑战赛提交版本。

赛事要求作品体现 AI 深度、实用性、用户体验以及安全可控性，但不规定医疗众筹平台的审批字段。以下规则是 CareFund-AI 为防止模型编造、保持证据可追溯而制定的产品规则，不是赛事官方医疗标准，也不代表任何真实平台审批要求。

机器可读配置：`backend/config/validation-policy.v1.json`。Validation 模块中的同名规则必须与该文件保持一致，测试会校验关键字段和阶段行为。

## 1. 必填事实

| 字段 | 类型 | 要求 |
| --- | --- | --- |
| `patient.medical_summary` | text | 必须由用户提供并确认；允许保留“尚未确诊”等不确定性，不要求虚构确定诊断。 |
| `treatment.estimated_cost` | money | 必须由用户确认，且必须存在当前申请材料中的明确文本支持。 |

申请显示名称 `patient_info.display_name` 由申请契约直接要求，不能为空白。资金表单中的已支付费用和筹款目标可留空；一旦进入事实集合，仍执行类型、冲突、来源和草稿引用校验。

## 2. 材料要求

- 至少上传一份状态为 `processed` 的 PDF、JPEG 或 PNG。
- `treatment.estimated_cost` 必须来自材料事实并引用有效 Evidence；用户自述不能替代费用材料。
- `patient.medical_summary` 建议提供材料支持，但用户自述本身可以满足必填要求，并持续显示来源提示。
- OCR 和文本匹配只证明“当前材料文字支持该表述”，不证明材料真实、有效或由医疗机构签发。

## 3. 阻断规则

以下任一情况产生 `blocking`，禁止生成、确认和导出：

- 缺少必填事实、已解析材料或费用材料来源。
- 必填事实未经过用户确认。
- 事实类型与 Policy 不一致，或文本、日期、金额格式非法。
- 同一字段存在不同取值；金额币种或数额不一致；日期不一致。
- 事实标记为 `conflicting` 或 `unsupported`。
- Evidence/Document 引用不存在、重复、跨申请、解析未完成或正文不支持事实。
- 已支付费用与预计费用的语义被混用。
- 事实或材料文本包含生成、篡改、夸大等提示注入指令。
- 申请、分析、草稿或操作请求的 ID、revision、状态不一致。
- 草稿遗漏事实、引用未知事实、修改事实原值/来源/限定词，或新增无事实支持的金额、日期、数字、诊断和困难程度描述。
- 确认记录缺失，或确认时间早于草稿创建时间。

系统不得通过删除 issue、只看 `can_finalize`、相信模型自报状态或客户端直接修改状态来绕过这些规则。

## 4. 允许继续的提示

以下问题保留在完整 ValidationResult 中并展示给用户，但不单独阻断流程：

- `info`：事实仅来自用户陈述，尚无材料独立支持。
- `warning`：建议补充患者与申请人关系、所在城市、治疗记录日期。
- `warning`：病情自述缺少材料来源，但用户已明确提供并确认自述。

发送给草稿模型的 `validation_issue_ids` 只包含 blocking ID；完整 info、warning、blocking 列表始终保存在后端分析结果中，用于界面展示、审计和导出。

## 5. 阶段门禁

### 允许生成草稿

- 分析结果存在且与当前 Application revision 一致。
- `can_finalize=true`，且不存在 blocking issue。
- 所有传入草稿的事实均已确认，未标记为 conflicting/unsupported。
- 同字段不存在不同原始值，事实不包含生成指令。
- 生成期间若申请 revision 改变，结果不得保存。

### 允许确认草稿

- Application 为 `draft_ready`，Draft 为 `generated`。
- 申请、分析、草稿和确认请求的 ID/revision 全部一致。
- 确认前使用当前快照重新运行正式 Policy 和草稿内容检查。
- 重新校验仍为 `can_finalize=true`；并发修改会返回状态冲突。

### 允许导出

- Application 为 `confirmed` 或已导出状态，Draft 为 `confirmed`。
- 草稿包含有效的 `confirmed_at`，且确认时间不早于创建时间。
- 申请、分析、草稿和导出请求版本一致。
- 导出前再次运行正式 Policy；任何新 blocking 或并发修改都阻止导出。

## 6. 建议字段与类型

- `patient.relationship_to_applicant`: text
- `contact.city`: text
- `treatment.recorded_date`: date
- `treatment.paid_cost`: money

建议字段缺失只产生 warning。任何已提供的建议字段仍必须满足类型、引用、冲突和内容安全规则。

## 7. 变更控制

提交版本冻结后，修改必填字段、材料要求、严重性或阶段门禁必须同时更新：

1. 两份 Policy JSON；
2. Validation 和 Backend 测试；
3. 本文档及相关 README；
4. 演示脚本和技术文档中的流程说明。

不得临时使用 demo、integration 或无 Policy 模式替代本规则并声称为正式业务行为。
