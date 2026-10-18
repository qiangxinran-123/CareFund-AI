# DeepSeek V4.1 Flash 接入与复测

2026-10-17 最新配置同步：用户提供的 `(4).yml` 已核对并同步到 `workflow.deepseek-extract.yml`，SHA-256 为 `560dc5f38b81d1ac9752eef123357fcfd7c6b2d25e8593214afdf0c5c3a0eae3`。模型和提示词与格式 v4 不变，新增的代码仅比本地已审源文件多一个末尾空行；四节点连线、三项字符串输出、无自动重试及默认失败终止已核对。原格式 v4 和最初预算依据均归档保留，累计额度不清零。第 89 行联网验证通过后继续新行，已真实观察到缺标记按既有政策处理，原始缺字段单独记账。87、88 行未知结果未重试。见 [导出核对](verification/full-csv-20261017/verified-question-guard-export.json)、[实时进度](verification/full-csv-20261017/live-progress.json)和[真实验证记录](verification/full-csv-20261017/question-guard-live.json)。后文保留各阶段当时状态。

2026-10-17 最新币种修订：用户发布提示词第 8 条规则后，另获授权的 6 次虚构真实抽取完成，原出错请求本次未复现无依据的币种偏好比较；5 条直接通过、1 条经复核为正确归因。6 份通过 D 离线接口，演示 policy 仍不放行。已核对用户的新导出，`workflow.deepseek-extract.yml` 现为该文件的原字节，旧导出归档；模型、参数及其他执行配置不变。新增 6 项评测复核测试后 A 77 项、契约 10 项通过，仍记录 1 个冗余确认币种的问题。见 [币种措辞修订与回归](verification/currency-wording-20261017/README.md)。下述发布版本 #2 及 9 次切换验证保留为 10 月 16 日历史记录，本次新版本号未独立观察。

2026-10-17 最新扩展测试：沿用现有配置又完成 100 次生成（94 抽取、6 草稿），没有接口失败或重试，原定自动判据全部通过；补充复核发现 1 处无依据的“平台常用人民币”警告措辞，修订候选尚未发布验证。94 份抽取通过 D 离线接口，演示 policy 均不最终放行。未修改生产代码、线上配置或两份 DSL 导出，未读取实际账单；详见 [扩展测试报告](verification/expanded-20261017/README.md)。

更新：2026-10-16。目标是保留 Dify 工作流调用接口，将模型供应商换成 DeepSeek 官方 API。

后续补充测试：另完成 30 次虚构案例的真实 Service API 调用，当时 30 份通过原有边界检查，补充内容复核为 29 条符合有限判据、1 条新增字段超出提示词范围。2026-10-17 已补 Python 字段范围门槛，离线回放时准确拒绝该错误响应，见 [修复记录](verification/scope-guard-20261017/README.md)。随后另完成 7 条最小真实摘录的线上抽取，均通过当前校验及有限内容判据，见 [摘录测试记录](verification/deepseek-real-20261017/README.md)。20 份虚构抽取和 7 份摘录分别通过 D 离线接口回放，演示规则仍全部阻断最终放行。原虚构结果见 [批量测试记录](verification/deepseek-batch-20261016/README.md)。原 60 案例已全部尝试，返回 59 份、历史接口失败 1 次，历史内容问题保留。下述 9 次为模型切换验证，单独计数。

最新单独授权的回归：新 CSV 的 20 条最小疾病输入和 4 个历史内容问题原输入共 24 次真实抽取通过本批判据，4 个原内容问题本次未复现；历史 HTTP400 未重试。24 份分别通过 D 离线接口，演示 policy 仍不放行。本轮沿用当前线上配置，未再次修改模型或提示词，见 [新 CSV 与回归报告](verification/csv-final-20261017/README.md)。

## 当前实际进度

- 已在用户的 Dify 工作空间安装官方 `langgenius/deepseek` 插件 0.0.24。
- 用户已直接在 Dify 保存供应商凭据，配置名 `DeepSeek-CareFund`，API Base URL `https://api.deepseek.com`。
- 两个原工作流均已切换到 **DeepSeek V4.1 Flash**，思考模式关闭、temperature=0、回复格式 `json_object`、最大输出 8192 tokens；失败自动重试保持关闭。
- 抽取保留原有系统规则，并增加既有 v2 中性措辞规则。4 个抽取、3 个草稿虚构案例在 Dify 编辑器真实运行成功，保存的 7 份响应已通过严格 JSON 解析及 `AgentService` 契约、身份、引用、状态和草稿逐字内容检查；抽取另按现有 expected.json 人工复核。
- 两个工作流均已发布为版本 **#2**：抽取于 2026-10-16 21:13:32、草稿于 21:16:08（北京时间）。本地 Python 到已发布 Service API 的抽取、草稿各一次冒烟复测成功（7.552 秒、12.856 秒），返回均通过 `AgentService` 检查及合成预期复核。
- 本轮共 9 次生成调用（7 次编辑器、2 次 Service API），另有 2 次 `/info` 只读查询以识别密钥归属；未重试。用户本地窗口输入顺序为第一把抽取、第二把草稿，报告只保存顺序和应用名，不保存密钥。
- 将新模型 5 份抽取响应离线映射到队友 D 的实际校验实现，输入输出契约和引用检查通过；演示业务规则仍将 5 份全部阻断（`can_finalize=false`），没有修改事实状态或校验门槛。这不是 B/D 在线端到端验收。
- 记录与可离线复验的合成响应在 [verification/deepseek-20261016](verification/deepseek-20261016/summary.json)，与 GPT 历史报告分开。
- 已收到用户提供的两份线上 DSL 导出，完整核对 YAML、模型、参数、三节点连线及提示词后，按原字节同步为 [workflow.deepseek-extract.yml](workflow.deepseek-extract.yml) 和 [workflow.deepseek-draft.yml](workflow.deepseek-draft.yml)。插件版本及完整依赖标识、文件 SHA-256 记录在上述 summary.json；导出没有携带密钥。
- 本地重新执行 A 模块 62 项测试和契约 10 项测试，全部通过。这些是离线测试，不证明 DeepSeek 的真实输出合格。
- 当前已验证的 GPT 导出、历史报告与冻结交付包保留。它们不代表 DeepSeek 已通过验收。

## 密钥与调用地址

| 用途 | 配置位置 | 说明 |
|---|---|---|
| DeepSeek 模型 API Key | Dify 设置 / 模型供应商 / 深度求索 | 用户直接填写到 Dify；不发到聊天，不写入源码或工作流 |
| DeepSeek API Base URL | 同一供应商表单 | `https://api.deepseek.com` |
| 抽取应用 API Key | Python 的 `DIFY_EXTRACT_API_KEY` 或现有隐藏输入窗口 | 仍是 Dify 应用密钥，不能替换成 DeepSeek 密钥 |
| 草稿应用 API Key | Python 的 `DIFY_DRAFT_API_KEY` 或现有隐藏输入窗口 | 仍须与抽取密钥分开 |
| Python 的 `DIFY_BASE_URL` | 本地/部署环境 | 保持 `https://api.dify.ai/v1`，不能改成 DeepSeek 地址 |

在原来的两个 Dify 应用内修改模型，不要求更换这两个应用密钥。如果另建测试应用，则必须使用对应新应用的专用密钥，不能混用。

供应商凭据会让同一 Dify 工作空间的成员通过应用调用该模型并消耗余额。界面中的“附加 Dify app_id 作为请求头”保持禁用即可。

## 工作流配置步骤

1. 用户在已打开的窗口填写 DeepSeek API Key 并点击保存，等待供应商验证通过。
2. 在原应用修改前导出当前 DSL，留作配置备份。
3. 抽取应用 `CareFund-信息抽取与追问-修订版`：将 LLM 节点的供应商改为深度求索，模型选择 **DeepSeek V4.1 Flash**，API 模型名为 `deepseek-flash`。
4. 草稿应用 `CareFund-已确认事实草稿-首版`：对“事实逐条成稿”节点做相同修改。
5. 本轮小型合成集已验证的参数为：思考模式关闭、temperature=0、回复格式 `json_object`、最大输出 8192 tokens。输出上限是限制，不是每次固定消耗量；若发生截断应停止并检查，不能直接重试或接受部分 JSON。小样本验证不是模型质量保证。
6. 保留开始变量 `request_json`、结束变量字符串 `result`，结束节点仍引用 LLM 的 `text`，不接思考内容。不得启用失败自动重试或自动降级到其他模型。
7. 检查抽取节点的系统提示词，并应用既有本地 v2 措辞规则：没有输入支持时，不代表平台提出要求，不宣称补材料能加快审核或提高通过率。规则来源为 `build_workflows.WORDING_RULE`；不要用未经核对的整段提示词覆盖线上已有规则。
8. 用合成请求测试当前编辑版本，检查 JSON、金额、不确定性、事实保留与引用；测试合格后再发布用于 API 复测。

部署本轮 DeepSeek 配置时使用 `workflow.deepseek-extract.yml` 和 `workflow.deepseek-draft.yml`。两份导出中的实际插件依赖均为 `langgenius/deepseek:0.0.24@9e12eef09973667f0eaf4f082af883167e1de88740b22e71e71488d020c3778a`，模型 ID 为 `deepseek-flash`。它们来自已完成测试的现有应用；本轮没有另外创建新实例进行重新导入测试，其他工作空间仍须配置自己的供应商凭据并验证。

原 `workflow.yml`、`workflow.extract-v2.yml`、`workflow.draft.yml` 保留为 GPT 历史配置；`python -m agent.build_workflows` 也仍生成 GPT 候选，不能用于重新生成本轮 DeepSeek 导出。

## 验证顺序

已复用现有四个抽取合成请求和三个草稿合成请求，完成 7 次编辑器工作流调用，无失败、无重试；未重复生成这些编辑器结果。随后完成已发布 Service API 的抽取、草稿各一次冒烟调用，调用前通过 2 次 `/info` 查询识别两把应用密钥，合计 9 次生成。供应商保存验证不计入这 9 次工作流调用，实际账单费用尚未核实。此次没有续跑源自真实医疗叙述的 MDCC 摘录。

- 抽取：两万元换算为 2000000 分；保留“可能、尚未确诊”；已有事实逐字段不变；三万材料/五万自述保留为两个来源并优先追问；不虚构平台建议、审核速度或证据。
- 草稿：只使用已确认事实；引用合法且正文逐条与事实相符；不执行事实文本中夹带的编造指令；固定警告和身份版本校验通过。
- 所有返回继续经过 `AgentService` 的正式契约、证据、状态与内容检查，不为迁就新模型放宽规则。
- 为这次迁移建立独立的运行目录并记录模型、思考模式、发布版本、请求哈希、调用次数与耗时。历史 GPT 报告应先另行归档，不能覆盖或合并计数。
- 7 个案例通过也只说明该合成集结果合格，不代表 B/D 集成、全部数据准确率或最终导出验收。

## 影响范围

`DifyRunner` 只调用 Dify `/workflows/run`，没有写死 GPT，因此当前无需新增 DeepSeek SDK 或改变 Python 接口。`contracts/`、B/D 源码及原有校验门槛均无需因供应商切换而调整。

本轮模型切换、9 次真实运行和两份 DSL 本地同步已完成。A/D 既有严重性映射及 pending 事实状态流转问题仍需团队确认，不因换模型自动解决。新的模型配置与文档尚未提交、推送或重打冻结交付包。

## 官方依据

- [Dify 官方 DeepSeek 插件](https://marketplace.dify.ai/plugin/langgenius/deepseek)：0.0.24，支持 V4.1 Flash。
- [插件模型参数定义](https://github.com/langgenius/dify-official-plugins/blob/main/models/deepseek/models/llm/deepseek-flash.yaml)：`thinking`、`temperature`、`max_tokens`、`response_format` 等参数。
- [DeepSeek 模型及价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：API 模型名 `deepseek-flash`。
