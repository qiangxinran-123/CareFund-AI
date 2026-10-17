# A 模块当前交付入口（2026-10-17 内容修复后）

上一轮复核发现的 A 警告、追问和指令草稿问题，已完成代码修复及保存响应回归。请先读本文件和 [修复报告](verification/content-fix-20261017/README.md)。旧报告与旧压缩包保留当时状态，其中的未修复标签不代表本次交付状态。

## 接入及复验

A 将用户描述和材料摘录整理为待确认事实及追问，再由已确认事实生成带 fact_id 引用的候选草稿。本包只提供 `agent/`，沿用小组 `contracts/schemas/`；比较后合入小组仓库，不覆盖其他成员目录。包中没有密钥、完整 CSV、真实医疗输入或响应、`.local/`，清单记录契约指纹。

在已有小组仓库根目录，使用 Python 3.10+：

```powershell
python -m pip install -r agent/requirements.txt
python -m unittest discover -s agent/tests
python agent/verification/content-fix-20261017/verify_saved.py
```

单元测试预期 108 项通过；回放预期 21 份虚构抽取事实不变、5 份正常草稿通过、1 份指令草稿按预期被拦截。回放不调用 API。旧 `content-review-20261017/replay.py` 入口也已转到本次策略复验。

正式工作流为 `workflow.deepseek-extract.yml` 和 `workflow.deepseek-draft.yml`。抽取 DSL 仍是用户 `(4).yml` 的已核对版本，SHA-256 为 `560dc5f38b81d1ac9752eef123357fcfd7c6b2d25e8593214afdf0c5c3a0eae3`。本次代码修复不改变线上模型和提示词，无须再手工发布 Dify。旧 GPT 工作流、构建器及 candidate 文件均不能替换当前正式 DSL；v5 提示词仅保留为历史候选，不是本次必需发布步骤。

Dify 内配置模型供应商密钥。B 服务端配置独立的 `DIFY_EXTRACT_API_KEY`、`DIFY_DRAFT_API_KEY` 及可选 `DIFY_BASE_URL`，每次请求创建独立的 service/runner：

```python
from agent.agent_service import AgentService, AgentError
from agent.dify_runner import DifyRunner

service = AgentService(DifyRunner.from_env(user=authenticated_opaque_user_id))
analysis = service.extract(extract_request)
# B/D 及用户完成确认、冲突处理后，使用有效事实快照：
draft = service.draft(draft_request)
```

**须调用 AgentService**：直接使用 DifyRunner 或 Dify 网页不会经过本次 A 展示规则和草稿输入策略。适配器同步阻塞，无自动重试、无模拟降级；超时可能远端已执行，不能立即重复生成。B 将 AgentError 映射为正式错误响应，不暴露 traceback 或患者正文。

## 本次完成的修复

- 完整模型响应先通过原有 Schema、身份、版本、来源、证据及事实状态校验；非法响应仍拒绝。随后由固定模板生成提醒和可选追问，事实正文、来源、ID、状态及版本完全保留。
- 提醒不再展示模型猜出的替代病名、病情关联或平台规定。歧义、冲突优先中性核对，缺信息可选补充；已明确的币种不重复追问，明确未知或拒绝补充时不强求，最多 3 条且 required=false。
- 已确认文本若夹带明显的编造、改规则等指令，草稿在调用模型前报错，要求核对来源事实；不偷偷删除原文或消耗生成调用。其余草稿继续通过逐字内容和引用门槛。
- service 内存保留边界校验后的 `last_extract_raw_response` 和无正文的 `last_extract_presentation_report`，失败清空，未向共享 JSON 契约添加字段。B 按受控存储规则留审计，不直接展示原模型响应或写入普通日志。
- 更正仍新增候选而非覆盖旧事实；相互矛盾的已确认版本不能一起成稿，离线生命周期测试已覆盖。

## 当前证据

| 检查 | 结果 |
|---|---|
| 离线测试 | A 108 项、共享契约 10 项、批量控制工具 20 项通过 |
| 60 条真实来源及 27 个虚构保存响应 | 81 份抽取事实不变、5 份正常草稿通过、1 份指令草稿拦截；原 20 个带发现案例均覆盖当前处理 |
| 全部 1,341 份批量可解析保存响应 | 1,339 份通过且事实不变；2 份历史缺字段响应仍拒绝 |
| 本轮新生成调用 | 0 次；原始响应、失败记录和调用账本未改写 |

详见修复目录中的 `saved-regression.json`、`bulk-saved-regression.json` 和 `local-checks.json`。这是保存响应的代码回归，不是重新生成、医疗专家标注或准确率测量。固定模板保证本次提醒措辞受控，有界词法策略不声称能识别全部改写或编码指令。

完整 CSV 共 84,712 行，原批次仍冻结在 1,350 次真实调用：1,338 次部分自动检查通过、11 次格式或网络失败、1 次上下文标记；111 次曾补齐追问 required，模型原始缺陷仍保留。没有冒充全量已跑完，也未将历史失败补记成成功。20 元是原授权上限，最新平台账单未读取，保守 token 费用上界不能当实际扣费。本包不自动续跑。

## 与 B/D 的职责边界

上述已发现的 A 内容问题已完成本轮修复。B/D 负责数据库事务、有效事实快照、确认流程、严重性映射、OCR 和最终导出；这属于完整集成验收，不是本次遗留的 A 修复待办。A 保持保守门槛：有未解决 issue ID 仍阻止草稿，不擅自删除 D 的 info 问题以放行。候选事实仍需用户核对及 D 验证，代码通过不等于材料真实或可以批准导出。

交付包可供队友接入和复验；本次未提交、推送或合并 GitHub。
