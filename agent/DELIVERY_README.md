# A 模块交付入口（v2）

交付日期：2026-10-16，Asia/Shanghai。文件名：CareFund-A-20261016-v2.zip。范围为 agent/；接收方为 B（后端集成）、D（独立校验）及 E（协调验收）。本包未发送给队友、未提交或推送。旧 v1 ZIP 保持原样，不用新版说明改写旧版验收结果。

## 当前结果

- 本地 Agent 测试62项、原契约测试10项及 pip check 通过。打包时在独立临时目录重新运行，结果见 ZIP 中 verification/local-checks.json。
- 真实抽取：四个合成案例完成，核心预期通过；其中“平台建议”措辞有一处观察，修订候选尚未验证线上发布。
- 真实草稿：2026-10-16 00:02完成三个合成案例，全部通过格式、版本、引用及固定内容检查。每条事实对应一章，属于固定排版首版。
- MDCC补充测试：200条原始记录只做本地请求格式检查；计划60次真实调用，实际尝试23次抽取，22份有效返回通过原定部分自动判据；3份追问理由存在无依据的“加快审核进度”。第23次HTTP400后停止，无重试。剩余37次未调用，本轮10条草稿全部未调用。
- 已直接查看Dify，模型显示AI消息额度200/200已用尽、未配置自有模型提供商。额度耗尽是当前阻塞；第23次错误由额度导致为结合页面作出的推断，原始错误正文未取回。没有充值或修改模型配置。
- B/D 当前本地目录仅有占位文件；本包没有实现或声称完成后端、独立校验、前端及端到端流程。

## 接收后按顺序做

1. 将 ZIP 解压到单独目录，先阅读本文件和 BD_INTERFACE_HANDOFF.md；不要把整个 ZIP 覆盖到团队仓库。
2. verification/contract-baseline.json 记录本包使用的正式契约指纹。B 对照团队当前 contracts/：若不同，先核对差异并运行测试，不覆盖或回退团队契约。
3. 在团队 feature/agent 分支审查后迁移 agent/，已有同名文件逐项比较。ZIP 内没有 contracts/、backend/ 或 validation/ 源码。
4. 在团队仓库根目录使用已有 contracts/ 安装及测试：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r agent/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s agent/tests -q
.\.venv\Scripts\python.exe -m unittest contracts.tests.test_contracts -q
.\.venv\Scripts\python.exe -m pip check
```

以上测试使用模拟网络，不会调用 Dify。ZIP 故意不附虚拟环境、缓存或密钥；接收方须有团队正式 contracts/，本包不是独立应用。

也可在已准备团队正式 contracts/ 和依赖的仓库根目录运行 `python verification/recheck_saved_responses.py`，离线复验包内7份历史真实响应。这不是重新调用Dify。

## B 的最小调用方式

```python
from agent.agent_service import AgentService, AgentError
from agent.dify_runner import DifyRunner

# 由后端的凭据配置系统注入环境；user 使用认证用户的不透明 ID。
service = AgentService(DifyRunner.from_env(user=authenticated_opaque_user_id))
analysis = service.extract(extract_request)
draft_candidate = service.draft(draft_request)
```

输入输出直接引用 contracts/schemas/agent.schema.json，不另建同名协议。DIFY_BASE_URL 默认 https://api.dify.ai/v1；DIFY_EXTRACT_API_KEY 和 DIFY_DRAFT_API_KEY 必须分别属于抽取、草稿应用。只调用草稿可只配置草稿密钥。程序不自动加载 .env；此前本地联调密钥没有持久保存，后端须自行配置。

Dify应用密钥用于后端调用工作流；模型供应商密钥用于Dify调用模型，两者用途不同。本包不附任一密钥。当前Dify赠送模型额度耗尽，恢复有效模型配置前不能声称接收方可立即完成在线验收。

适配器同步阻塞，异步后端应在线程池中调用；超时90秒、无重试、无模拟降级。捕获 AgentError 映射到团队错误响应。B 在保存事务内重新检查 revision，D 独立检查输入事实、证据支持及最终完成条件；A 返回成功不能直接授权导出。

## Dify 与验收材料

- workflow.yml：已验证抽取工作流导出。
- workflow.draft.yml：已导入并验证的独立草稿工作流。
- workflow.extract-v2.yml：仅本地措辞修订候选，不能冒充已验证线上版本。
- DIFY_DRAFT_SETUP.md：导入、发布与专用密钥设置步骤。
- LOCAL_HANDOFF_STATUS.md、DRAFT_IMPLEMENTATION_STATUS.md：真实结果与限制。
- KNOWN_ISSUES.md：上线前待处理事项、影响及责任边界；MDCC_EVALUATION_RESULTS.md：中断测试的实际结果。
- ZIP 的 verification/：四个抽取及三个草稿的合成输入、实际响应、脱敏运行摘要及契约指纹。摘要中的本机绝对路径已改成包内相对路径；原始报告保留在开发机 .local/ 中。
- verification/mdcc-summary.json：MDCC的计数、逐案例状态与复核标记，不含真实摘录或患者正文。verification/batch/synthetic-cases.json：本轮30条虚构压力案例，尚未进行本轮真实调用，不是额外30条通过证据。
- MANIFEST.json：除自身外的全部 ZIP 成员大小及 SHA-256；ZIP 外同名 .sha256 文件校验整个压缩包。

夹带指令测试只证明该样例未导致扩写，原文仍被引述，不是可发布文案或全面抗注入验收。输入事实真实性、确认有效性、材料真伪及用户编辑后的复核不由本模块证明。

字段表、ID 分配、更正替换、冲突与多记录、校验 issue 传入方式和版本事务，按 BD_INTERFACE_HANDOFF.md 与 B/D 确认后再集成。

## v2 相对 v1 的变化

新增MDCC适配、有限批量测试工具与14项离线回归，新增HTTP已知错误码脱敏、审核效果措辞复核和旧报告防覆盖；扩展未发布的抽取措辞候选。正式契约、原已验证抽取导出保持原样，没有替其他模块实现功能。

包内没有MDCC CSV、200条原始请求、30条真实摘录、来源行号、真实摘录响应、剩余37条待调用套件或本地下载器。因此MDCC文档里的 .local/ 路径是开发机证据位置，解压后不存在属于预期；不能直接照着历史续测命令运行。可用的包内虚构案例需显式指定 `--suite verification/batch/synthetic-cases.json --report agent/.local/mdcc/new-synthetic-status.json`，只有在需要在线验收且凭据/模型可用时才执行；本次打包不执行任何在线调用。
