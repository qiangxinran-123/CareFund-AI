# A 模块 GitHub 交付说明

本次将已验收的本地 v2 交付内容迁入团队 `feature/agent` 分支，基于2026-10-16拉取的 `main`（`fe89bd1b857b5142365ffefc2286a8fe5f7024f7`）。仅新增/修改 `agent/`，不修改共享契约及其他成员模块；合并需非作者成员审查。

## 接收方从这里开始

1. 阅读 `README.md` 的模块说明和 `BD_INTERFACE_HANDOFF.md` 的待确认清单。
2. 查看 `KNOWN_ISSUES.md` 和 `MDCC_EVALUATION_RESULTS.md`；已完成基本实现及初步真实验证，不是全系统最终验收。
3. 使用仓库正式 `contracts/`，安装 `agent/requirements.txt`，执行以下离线检查。

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r agent/requirements.txt
.\.venv\Scripts\python.exe -m unittest discover -s agent/tests -q
.\.venv\Scripts\python.exe -m unittest contracts.tests.test_contracts -q
.\.venv\Scripts\python.exe agent/verification/recheck_saved_responses.py
.\.venv\Scripts\python.exe -m pip check
```

预期为62项Agent测试、10项契约测试通过，并复验7份历史真实合成响应。复验使用保存结果，不会调用Dify。报告防覆盖测试故意触发一次“Report already exists”；最终为OK且退出码为0属于预期。

## 证据与目录

- `verification/extract/`、`verification/draft/`：4个抽取、3个草稿的合成请求及真实响应；同目录上级的摘要保留历史运行信息。
- `verification/recheck_saved_responses.py`：可在任意工作目录执行的离线复验入口，路径已按本仓库布局调整。
- `verification/mdcc-summary.json`：仅含统计、案例状态、指纹及复核标记，不附真实摘录或响应。
- `verification/batch/synthetic-cases.json`：20条虚构抽取、10条虚构草稿压力案例；本轮尚未在线调用，不是新增30条成功证据。
- `verification/contract-baseline.json`：原交付使用的契约文件指纹；本次已核对团队main的文件内容一致，允许Git检出造成的CRLF/LF差异。
- `verification/local-checks.json`：冻结v2 ZIP打包时的独立目录检查记录；本次迁入仓库后另行重跑检查，结果记录在PR说明。

`DELIVERY_README.md` 描述独立ZIP布局，该ZIP根目录的 `verification/` 在GitHub仓库中归入 `agent/verification/`，所以仓库内使用本页命令。历史说明中的 `.local/` 是原开发机证据位置，未上传、不应期待在克隆后出现。原v1/v2压缩包未上传，源码直接供团队审查；历史交付文档中“尚未提交”等文字是当时快照，本次GitHub交付状态以分支和PR为准。

## 当前限制

MDCC计划60次，本轮实际尝试23次抽取、22份有效返回；3份存在无依据的审核加速措辞，第23次HTTP400后停止，剩余37条未调用。Dify当前赠送模型额度200/200已用尽；没有恢复额度、充值或新增真实调用。

本地 `workflow.extract-v2.yml` 已扩展措辞规则，但未发布或复测；线上仍使用原工作流。草稿是固定逐条排版首版，不支持自由润色，不证明输入事实真实。B/D集成、最终状态/版本/导出控制及PR审查合并仍待完成。不要把离线通过或提交PR当作上述事项完成。

本次没有上传密钥、真实医疗叙述、原始CSV、来源行号、`.local/`、虚拟环境、缓存或其他成员代码。后续在线验收需自行在本地配置两个Dify应用凭据和可用的模型供应商，密钥不得写入仓库。

## 2026-10-16 A/D首轮适配补充

已收到D源码并在独立目录执行离线接口检查；此前“B/D未集成”的描述现细化为：4份历史合成抽取输出可被D接收，A62项、D54项和契约10项测试通过，实际草稿放行及后端端到端流程仍未打通。结果见[AD_INTEGRATION_STATUS.md](AD_INTEGRATION_STATUS.md)及`verification/ad-check-summary.json`。本轮仅补充A交接文档和脱敏检查记录，未修改生产代码、D源码或共享契约。
