# A 模块 Dify 抽取与草稿接口使用说明

这是 CareFund-AI 的 Agent 接口基础包，用于先验证模块边界，再接入真实 Dify 工作流。只新增 agent/ 内文件，原 contracts/ 和其他成员目录保持不变。不是已完成的智能申请助手。

接收交付包时先读 [DELIVERY_README.md](DELIVERY_README.md)，其中包含迁移步骤、契约指纹说明和 B/D 接入顺序。

## 1 当前完成情况

已实现正式 Schema 的请求与响应校验、申请 ID 与 revision 一致性检查、证据引用存在性检查、重复 ID 检查、新候选事实确认状态限制、已有事实不可原 ID 改写、草稿引用检查，以及明确标记的模拟演示。

已整合用户导出的 workflow.yml 与抽取提示词，并完成四个合成案例的真实抽取 API 联调。独立草稿 DSL、专用调用入口、事实逐条成稿内容检查和本地合成联调入口已实现；用户导入、发布新草稿应用并更换专用密钥后，于2026-10-16完成三个合成案例的真实草稿调用，全部通过正式契约、引用和固定内容检查。用户确认交互及后端集成尚未完成。

历史交接为 23 项 Agent 测试、10 项原契约测试。当前 Windows / Python 3.13.15 / jsonschema 4.26.0 环境已通过 62 项 Agent 测试（含本轮新增14项评测及错误诊断回归）、10 项契约测试和依赖检查。这些离线测试中的网络是模拟；真实抽取结果与草稿进度分别见 LOCAL_HANDOFF_STATUS.md 和 DRAFT_IMPLEMENTATION_STATUS.md。MDCC 补充评测与原交付分开记录，见 MDCC_EVALUATION.md 和 MDCC_EVALUATION_RESULTS.md。

## 2 今晚在 Windows 电脑上的操作

1. 解压交付包。进入 CareFund-AI-main 文件夹；这里应同时能看到 agent、contracts、backend。
2. 用 VS Code 打开这个文件夹，然后打开终端。
3. 按顺序执行以下命令。使用虚拟环境解释器的完整相对路径，无需修改 PowerShell 的脚本执行策略。

```powershell
py -3 --version
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r agent/requirements.txt
.\.venv\Scripts\python.exe -m unittest contracts.tests.test_contracts -v
.\.venv\Scripts\python.exe -m unittest discover -s agent/tests -v
.\.venv\Scripts\python.exe -m agent.demo
```

建议 Python 3.10 或以上；当前本地测试版本为 3.13.15。第一条命令失败时先停止，把报错发给协助开发者确认 Python 安装。

两组测试当前应分别显示 Ran 10 tests 和 Ran 62 tests，以及 OK。演示应打印 JSON，并明确显示 MOCK。模拟问题固定，用于检查管道，不代表真实智能追问结果。

ZIP 下载不包含 Git 历史。晚点需要克隆仓库，在 feature/agent 分支上只复制本包 agent/ 新增内容。不要用整个旧 ZIP 覆盖队友最新仓库。此包没有提交、推送或修改远程仓库。

## 3 给 B 的接入说明

```python
from agent.agent_service import AgentService, AgentError

# runner 可使用第7节提供的 DifyRunner。
# runner(operation, request) -> dict
# operation: extract 或 draft
service = AgentService(runner)
result = service.extract(extract_request)
# 或 service.draft(draft_request)
```

AgentService 直接引用 ../contracts/schemas，不复制模型定义。runner 接收输入的深拷贝并返回规范化字典。runner 网络异常转为 AgentError，不静默退回 Mock；B 需要将异常映射到团队统一错误响应，避免向用户展示异常内部内容。

所有结果均为候选。后端仍必须检查当前 revision、引用完整性、内容及状态，不得仅因本模块返回成功而允许导出。日志不要记录患者正文或密钥。

已有候选事实必须完整原样返回才能保留原 ID；修订内容应使用新候选 ID，由 B 处理替换与版本更新。现在强制模型完整保留所有输入已有事实；遗漏或篡改会报错。B 必须传入当前版本完整事实及对应证据，并在保存时重新检查 revision；不能把模型结果当成数据库直接覆盖指令。

## 4 需要 A B D 一起确认的约定

1. field 字段的统一清单与必填项。现有 Schema 只限制格式，不能凭示例中的城市问题认定城市是业务必填项。
2. fact_id/question_id 由哪一层分配及如何跨重试保持稳定。证据 ID 必须复用 B 输入提供的真实 ID。
3. 用户回答如何规范化进入 user_input，以及 user_correction 与原事实的替换关系。
4. D 的校验问题如何传给追问流程。当前抽取请求无校验结果字段，草稿请求仅有 validation_issue_ids，不能按 ID 猜测详情。
5. 本基础包采用保守策略：有任何 validation_issue_ids 就阻止生成；草稿仅接受 user_confirmed=true 且不为 conflicting/unsupported 的事实。它不等于团队已批准的完整业务规则。若只应阻止严重问题，应由团队确定调用前置条件，必要时走契约变更流程。
6. user_input 和 user_correction 事实可以是 pending；确认只说明认可表述。材料来源事实即便 confirmed，也不代表真实性核验。

## 5 Dify 工作流

两个操作使用独立工作流。workflow.yml 是已经真实验证的抽取导出；workflow.draft.yml 沿用导出的 DSL 0.7.0 和模型插件配置，已由用户在当前 Dify 实例导入、发布并通过三个合成案例的真实调用。再次部署的步骤见 DIFY_DRAFT_SETUP.md。

抽取流程：接收规范化请求 → 模型依据输入提取候选事实并追问 → 解析结构化输出 → 返回给 Python 边界校验。

草稿流程：由后端准备符合前置条件的事实 → 模型生成带 fact_ids 的章节 → 解析结构化输出 → 返回 Python 校验 → 后端与 D 做独立检查。

输入均视为数据，不能执行材料里夹带的指令。提示词初稿在 prompts/。实际模型的结构化输出能力、上下文长度、错误行为及费用需在选型后验证。先用合成案例，不发送未经授权的真实患者数据。

## 6 内容级风险与验收

一个章节引用正确 fact_id，依然可能在文字里虚构额外费用。草稿首版因此增加固定排版内容检查，拒绝原始已确认事实以外的扩写、改金额、丢失不确定性、遗漏事实或改变来源。此检查不核验输入事实本身，也不能判断原始证据是否支持输入事实，后者仍须 B/D 完成。

接入模型后必须验证：正常案例、缺失信息、金额与日期冲突、要求编造或夸大、材料内提示注入、模型非法 JSON、调用失败、用户修订导致旧结果失效。由 A 修复生成问题，D 做独立核验，B 管理版本与导出门禁。


## 7 本次新增的真实调用入口

workflow.yml 为用户最新导出文件的原样副本；prompts/extract.md 与其中 SYSTEM 文本一致。没有修改共享契约或其他成员源码。

Dify 调用协议参考（2026-10-15查阅）：
- https://docs.dify.ai/en/api-reference/guides/get-started
- https://docs.dify.ai/en/api-reference/guides/workflow

先在 Dify 发布当前工作流，再在该应用的 API 访问页面创建应用 API 密钥。这个密钥不是 OpenAI 模型密钥；不要发到聊天、前端或 Git。模型调用仍使用你在 Dify 中配置的供应商。

在电脑上完成第2节安装后，运行：

```powershell
.\.venv\Scripts\python.exe -m agent.run_extract agent/examples/extract-request.json --user demo_user_001
```

命令行会隐藏输入 Dify 应用密钥。也可由部署系统注入 DIFY_EXTRACT_API_KEY。DIFY_BASE_URL 默认 https://api.dify.ai/v1。后台程序不会自动读取 .env 文件。

给 B 的调用方式：

```python
from agent.agent_service import AgentService
from agent.dify_runner import DifyRunner

# 必须由后端提供已认证用户对应的不透明标识，不使用姓名、电话。
service = AgentService(DifyRunner.from_env(user="opaque_user_001"))
result = service.extract(extract_request)
```

输入经过正式 Schema 校验后，适配器向 /workflows/run 发送 inputs.request_json 字符串、response_mode=blocking 和 user；只接受 succeeded 响应，解析 data.outputs.result 后交回 AgentService 做契约和引用检查。非法JSON、重复JSON键、失败状态、版本不符、未知证据、遗漏已有事实都拒绝；无自动重试、无模拟降级。超时不代表服务端执行取消，请先检查 Dify 日志，不要盲目重试。

默认超时90秒，响应大小上限4MiB，禁用HTTP重定向，错误不包含服务端响应正文。本入口同步阻塞；B 如在异步服务中调用，应使用线程池，避免阻塞事件循环。

DIFY_DRAFT_API_KEY 供独立草稿工作流使用，未配置时明确报错；不会自动使用抽取密钥。现在支持仅配置草稿密钥；两个操作都配置时，密钥必须不同。草稿实现见第10节，专用应用已发布并通过本次三个合成案例的真实调用；本地联调密钥不持久保存，后端部署仍需另行配置。

## 8 验证范围与仍需完成的事

新增10项离线测试：真实适配器到边界校验的组合、HTTP鉴权错误脱敏、超时不重试、失败状态、缺失输出、非法JSON、未配置草稿、URL检查、过期版本与已有事实遗漏。网络响应被模拟，不代表已完成真实API联调。

用户在 Dify 界面测试：两万元换算、模糊金额/未确诊、已有事实保留、三万元材料证据引用、三万与五万冲突分别保留并追问。仅有用户提供的结果，不是自动化评测或准确率保证。

抽取端仍主要做格式、编号、引用存在性和状态检查，不证明输入金额语义或证据支持。草稿端增加了固定排版内容检查。抽取允许相同 field 的冲突候选，B 不得仅按 field 去重覆盖；草稿首版遇到相同 field 的不同 value 会先阻止。D 仍须独立识别冲突，模型返回成功不能作为导出许可。

字段清单中 patient.relationship_to_applicant、treatment.paid_cost、documents.diagnosis_proof 仍为暂定；共享契约尚未批准业务字段清单。工作流当前只抽取列出的有限字段，不是完整业务资料表。

下一步：与 B/D 确认字段和合并规则 → B/D 集成与端到端验证；另需发布并验证抽取措辞修订候选。

## 9 本地接手验证（2026-10-15）

已在 Windows、Python 3.13.15 独立虚拟环境中安装本模块依赖，jsonschema 为 4.26.0，referencing 为 0.37.0。本次重跑原契约测试 10 项通过，Agent 测试 27 项通过（原 23 项 + 脱敏错误透传回归 1 项 + 联调启动器离线测试 3 项），`pip check` 通过，MOCK 演示通过。测试中的网络调用为模拟，不构成真实 API 成功记录。

服务层现保留适配器已经脱敏的 `AgentError`，使真实联调能区分 HTTP 401、输出格式错误等原因；其他异常仍统一转换为 `Agent runner failed`。

交接包提供额外本地入口，可依次运行 `agent/examples/extract_cases/` 的四个合成请求。这些请求及 expected.json 原样复制自原始 project_memory/test_cases，交付后不依赖交接包外层目录：

```powershell
.\.venv\Scripts\python.exe -m agent.live_check --gui
```

窗口可填写 HTTPS API 服务地址与隐藏的抽取应用密钥。若已通过环境注入密钥，则直接开始调用。密钥不写入配置、报告或命令行；不自动加载 `.env`。也可以去掉 `--gui`，使用原生终端隐藏输入。

联调状态写入 `agent/.local/live-status.json`，成功返回的合成响应写入同目录的带时间戳子目录；该目录由 `agent/.gitignore` 排除。只处理交接的合成案例，不接受任意患者请求。请求经过正式 Schema 校验后才调用 Dify；每个案例只调用一次，首个失败即停止，不重试、不降级。超时需先查 Dify 日志再决定下一步。

状态 `schema_and_references_passed` 只表示真实返回通过程序边界检查；`semantic_review` 仍需逐条对照 `project_memory/test_cases/expected.json` 人工核对。启动器自身的模拟测试不写入真实联调报告。当前实际联调进度见 `agent/LOCAL_HANDOFF_STATUS.md`，不要把上述本地测试当作真实模型验收。

本次接手已完成 4 次真实 Dify 抽取调用，四个交接合成案例均通过程序边界检查与核心预期复核，未重试、未 Mock 降级。案例 02 出现未经输入支持的“平台建议补充”措辞，已在接手记录中列为后续工作流改进项。具体申请版本、用时、观察和结果路径见该记录；本次结果不能证明任意输入可靠或草稿/端到端已完成。

## 10 独立草稿首版

交接清单：[BD_INTERFACE_HANDOFF.md](BD_INTERFACE_HANDOFF.md)。导入与运行：[DIFY_DRAFT_SETUP.md](DIFY_DRAFT_SETUP.md)。本地排版效果：[DRAFT_LOCAL_PREVIEW.md](DRAFT_LOCAL_PREVIEW.md)（确定性预览，非模型返回）。当前验收状态：[DRAFT_IMPLEMENTATION_STATUS.md](DRAFT_IMPLEMENTATION_STATUS.md)。

草稿前置条件由 `AgentService.validate_draft_request()` 检查，失败时不索取密钥、不调用 API。原有保守条件继续生效，另增加同字段不同值阻止和排版长度预检查。一条事实对应一个章节，保留来源与完整原值；每章必须准确引用该 fact_id。生成结果必须与固定规则逐字一致，不能自由润色或跨事实合并；空格/标点不一致也会拒绝，需检查已发布提示词版本，不会自动改写模型输出。

```powershell
.\.venv\Scripts\python.exe -m agent.run_draft agent/examples/draft-request.json --user opaque_demo_user
.\.venv\Scripts\python.exe -m agent.draft_live_check --gui
```

第一条处理单个规范化请求；第二条仅运行三个随包合成请求，使用草稿应用的隐藏密钥输入窗口，结果写入被 Git 忽略的 `agent/.local/draft-live-status.json`。仅使用 `DIFY_DRAFT_API_KEY`，不会借用抽取应用密钥。草稿请求没有原始证据正文，B/D 必须另行检查引用是否属于当前申请并支持事实。首版不适用于任意自由文案，用户手工编辑后的结果也必须重新校验。

抽取措辞的本地修订为 workflow.extract-v2.yml / prompts/extract-v2.md，修正未经提供依据的“平台建议”等措辞；原始已验证导出保持不变。候选文件未自动发布，尚不能声称线上措辞已修复。

## GitHub 仓库交付入口

本分支的迁移与离线复验步骤见 [GITHUB_DELIVERY.md](GITHUB_DELIVERY.md)，已知问题见 [KNOWN_ISSUES.md](KNOWN_ISSUES.md)。历史ZIP的 verification/ 在仓库内置于 agent/verification/；真实医疗摘录及本地运行目录未上传。

2026-10-16收到D代码后的首轮离线接口检查、严重性门槛差异及材料核对流程待确认项见[AD_INTEGRATION_STATUS.md](AD_INTEGRATION_STATUS.md)。这次补充更新交接状态，生产代码和放行规则保持原样。
