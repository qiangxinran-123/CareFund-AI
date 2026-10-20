# CareFund-AI 统一接口契约 V1

本目录定义 CareFund-AI 四个技术模块之间的稳定数据边界。它只描述契约，不实现 FastAPI 路由、React 页面、OCR、事实核查算法或 Dify 工作流。

## 模块职责与调用方向

```text
Frontend ──REST /api/v1──> Backend
                              ├──适配──> OCR / 文件处理
                              ├──规范化输入输出──> Agent
                              └──规范化输入输出──> Validation
```

- Frontend 只调用 Backend REST API，不直接调用 Agent、Validation 或 Dify。
- Backend 是 Application、附件集合、revision、状态转换及统一响应的唯一权威来源，并负责服务编排。
- Agent 只产生候选事实、追问和候选草稿文本；它不能修改申请状态，不能生成不存在的证据引用，也不能输出平台审核结论。
- Validation 检查结构、缺失、冲突和证据引用；它不能修改用户原始输入。`can_finalize` 必须由确定性规则计算，不能直接采用 LLM 返回值。
- 所有模型输出都是候选结果，Backend 必须执行 Schema、引用完整性、revision 和状态校验。

## 文件与模型

- `schemas/common.schema.json`：版本、ID、UTC 时间、金额、统一错误、分页和健康检查。
- `schemas/application.schema.json`：Application、PatientInfo、状态、创建/更新请求与响应。
- `schemas/evidence.schema.json`：上传文档、Evidence、Fact、来源类型、验证状态及受限 FactValue。
- `schemas/agent.schema.json`：Backend 与 Agent 适配器之间的抽取、追问、答案和候选草稿输入输出。这里定义的是内部规范化接口，不虚构 Dify 自身 REST 路径。
- `schemas/validation.schema.json`：校验请求/结果、问题、异步分析任务和聚合分析结果。
- `schemas/draft.schema.json`：草稿、章节、确认请求及 V1 JSON 导出。
- `openapi.yaml`：OpenAPI 3.1 公共 Backend REST API。文件采用 JSON 表示；JSON 是合法的 YAML 1.2，便于仅用 Python 标准库解析。
- `examples/`：一致的虚构 Mock JSON，可供四个模块独立开发。
- `tests/test_contracts.py`：Schema、OpenAPI、示例与跨对象业务前置条件测试。

OpenAPI 通过外部 `$ref` 直接复用上述 Schema。禁止复制字段后分别维护两套模型。

每个 Schema 文件均声明默认根模型：Common=`ErrorResponse`、Application=`ApplicationResponse`、Evidence=`Fact`、Agent=`AgentExtractResponse`、Validation=`ValidationResult`、Draft=`Draft`；其他请求/响应模型通过对应 `$defs` 引用。

## 命名、ID、时间、金额与 null

- API 前缀固定为 `/api/v1`；JSON 字段使用英文 `snake_case`。
- ID 是稳定、不透明的字符串，调用方不得从 ID 推断业务含义。
- 时间戳使用 RFC 3339 UTC，必须以 `Z` 结尾；纯日期使用 `YYYY-MM-DD`。
- 金额使用 `Money.currency`（ISO 4217）和非负整数 `amount_minor`；禁止浮点金额。
- 缺失字段表示“调用方未提供”；仅当 Schema 明确允许时，`null` 表示“已知当前无值/未知”。数组在模型中均明确声明，响应数组应返回 `[]` 而不是 `null`。
- `schema_version` 当前固定为 `1.0`。

## 事实、证据与确认

- `source_type=user_input` 或 `user_correction` 的事实可以保留，但不能伪装成文件证明。
- `source_type=document` 的 Fact 至少引用一个既有 `evidence_id`。
- `verification_status=supported` 只表示当前提交材料的文本支持该字段，不代表凭证真伪经过权威核实。
- `user_confirmed=true` 只表示用户认可表述，不表示医疗诊断成立、材料真实或平台审核通过。
- OCR 只提供提取结果，不得直接推断材料真实有效；未知页码必须为 `null`，不得编造。
- JSON Schema 能检查单对象结构，但 Evidence/Fact/Issue/Draft 的引用是否真实存在必须由程序跨对象检查。

## Application 与 Draft 状态

Application 状态由 Backend 维护：

```text
collecting -> reviewing -> ready_for_draft -> draft_ready -> confirmed -> exported
```

实际实现可以在失败或用户编辑后回到较早状态，但每次转换必须由 Backend 的显式规则授权。Agent、Validation 和 Frontend 均不能直接改变状态。

Draft 状态为 `generated`、`confirmed`、`stale`。用户输入或附件集合变化时，Backend 递增 `Application.revision`，并使旧分析、确认结果和绑定旧 revision 的草稿失效。只有满足以下条件才可确认或导出：

1. Draft 的 `application_revision` 等于当前 Application `revision`。
2. 请求中的 `draft_revision` 等于当前 Draft 版本。
3. Draft 未标记为 `stale`。
4. 最终确定性校验结果允许完成，且关键 Fact/Evidence 引用完整。
5. 导出对象为已确认草稿；V1 只保证 JSON 申请包，不保证 PDF/DOCX。

这些条件需要 Backend 事务与并发控制，不能仅靠 JSON Schema 保证。

## 上传、分析任务与重试

- 上传接口一次接收一个 `multipart/form-data` 文件。V1 媒体类型为 JPEG、PNG、PDF；Backend 负责大小限制、文件存储与处理状态。
- `POST .../analyze` 返回 HTTP 202 `AnalysisJob`。Frontend 使用任务 URL 轮询，成功后再读取 `GET .../analysis`。
- 调用方为分析请求提供 `idempotency_key`。相同 Application revision、相同请求意图和相同 key 必须返回可识别的同一任务，而不是重复创建。
- 网络超时表示结果未知；客户端应使用同一 key 查询或安全重试，不能把超时直接当作任务失败并生成新 key。
- PATCH、回答、草稿、确认和导出均携带 expected revision；过期请求返回 HTTP 409 `STATE_CONFLICT`。
- 业务失败使用相应 4xx/5xx 和统一 `ErrorResponse`，禁止 HTTP 200 包装失败。

## Mock JSON 的使用

- Frontend：用四份示例制作 API Mock；字段和枚举必须以 Schema 为准。
- Backend：以 OpenAPI 实现公开路由，并在服务边界校验请求/响应；通过适配器转换 Agent/Dify 输入输出。
- Agent：以 `AgentExtractRequest/Response`、`AgentDraftRequest/Response` 为规范化边界，仅输出候选内容。
- Validation：以 `ValidationRequest/Result` 为边界，并实现 ID 引用、金额/日期、来源语义和确定性 `can_finalize` 规则。

示例全部为虚构数据，不构成医疗诊断、凭证真实性判断或真实平台审批承诺。

## 运行测试

测试使用 Python 标准库 `unittest` 和轻量依赖 `jsonschema`：

```bash
python -m pip install "jsonschema>=4.18,<5"
python -m unittest contracts.tests.test_contracts -v
```

不要因此在项目根目录引入大型依赖或运行时框架。测试分别覆盖：Schema 可解析性、OpenAPI 引用、示例校验、非法枚举/金额/日期/required，以及跨对象引用和 revision 前置条件。

## 版本兼容策略

V1 路径为 `/api/v1`，Schema 主版本为 `1`。可选字段的兼容新增可经团队审查后在 V1 内迭代；调用方必须容忍审查通过的新可选字段时，相关 Schema 才能放宽 `additionalProperties` 策略。字段重命名、删除、类型变化、required 增加或语义变化属于破坏性变更，必须升级 API 主版本或执行统一迁移。所有契约变更应同时更新 Schema、OpenAPI、示例和测试。
