> **2026-10-17 修复后交付入口：** 请先读 [CURRENT_HANDOFF.md](CURRENT_HANDOFF.md) 和 [代码修复报告](verification/content-fix-20261017/README.md)。此前警告、追问和指令草稿问题已由 A 代码处理，108 项单元测试通过；原 87 份结果及全部 1,341 份可解析批量响应已离线回归，0 次新 API 调用。以下问题和计数保留各历史阶段状态，不代表本轮仍未修复。

# A / D 首轮离线接口检查

2026-10-17 币种措辞修订后，另 6 份虚构真实 API 抽取响应通过 D 实际实现的离线回放，契约、身份版本、问题引用与输入不变检查通过，演示 policy 均 `can_finalize=false`。这 6 份与此前 94 份独立记账，未改变 D 源码或引入 B 事务。见 [币种修订回归](verification/currency-wording-20261017/README.md)。

2026-10-17 扩展批次：94 份新增真实 API 抽取响应分别映射到实际 D 离线实现，输入／输出契约、身份版本、问题引用与输入未变检查通过，演示 policy 均 `can_finalize=false`；冲突费用案例正确产生 blocking 的 `inconsistent_amount`。6 份新增草稿未混入这 94 份或宣称完成导出验收。A 补充内容复核另发现 1 处警告措辞问题，D 接口接受不抵消该问题。详见 [扩展测试与 D 摘要](verification/expanded-20261017/README.md)。

2026-10-17 再补充：新 CSV 20 条最小疾病输入及 4 条历史内容案例的真实 A 响应，均已通过实际 D 离线接口回放，演示 policy 全部 can_finalize=false。两套 6 份 Schema JSON 内容一致，字节指纹不同，分别留档。见 [新 CSV 回归与 D 摘要](verification/csv-final-20261017/README.md)。这仍不等于 B/D 在线端到端验收。

后续补充：DeepSeek 切换的 5 份抽取、随后虚构批量的 20 份抽取、2026-10-17 最小真实摘录的 7 份抽取，已分别完成实际 D 离线回放，契约和引用等检查通过，演示 policy 均不放行。摘录正文及完整回放只保存在本地忽略目录。虚构批量另发现 1 条 A 提示词字段越界问题，不能因 D 接口接受而视为合格。详见 [DeepSeek 批量记录](verification/deepseek-batch-20261016/README.md) 和 [摘录记录](verification/deepseek-real-20261017/README.md)。以下保留首轮 4 份历史输出的检查记录。

日期：2026-10-16（Asia/Shanghai）。A基线提交为cc29e6de047c49d20c79d628ed4dfa6a839c104c。D来自队友提供的validation.zip，原包SHA-256为7ec5a840f747ca9fd776a8e3c5bb5b449f0f232193d176b141372bb430fc49ec。

## 已完成的范围

在独立本地目录组合A、当前共享contracts及D源码，排除D包内虚拟环境和缓存；双方生产代码均原样保留。实际使用Python 3.13.15，A的62项测试、D的54项测试、契约10项测试通过。

4份历史真实合成抽取响应先通过AgentService.extract的边界检查，再转换为ValidationRequest调用D实际实现。转换为：documents取自extracted_documents[*].document，evidence取对应evidence数组展平，facts取candidate_facts，申请ID、revision及schema_version保持一致。

D均正常返回正式ValidationResult，响应版本和问题引用检查通过，输入未被修改。D演示policy下4份均返回can_finalize=false，原因包括缺少材料/字段、用户未确认、材料事实pending和金额冲突。金额冲突案例确实产生blocking的inconsistent_amount。结果是接口可接收并执行规则，不是4份均达到最终放行条件。

完整本地检查摘要见verification/ad-check-summary.json。没有新Dify调用，没有真实患者内容，也没有引入D代码作为A的运行依赖。D包未提供其contracts基线，已验证当前契约运行兼容，尚不能断言双方最新远程契约版本一致。

## 已复现的问题与责任

| 事项 | 实际行为 | 后续决定 |
|---|---|---|
| info问题与成稿门槛 | D自带正常演示返回can_finalize=true，同时有用户自述来源的info问题；若全部issue_id传给A，A在调用模型前拒绝 | A/B/D明确草稿生成及最终导出的不同前置条件和严重性映射，保留完整issues，不擅自删除提示或放宽门槛 |
| 材料事实核对后的状态 | A新抽取事实保持pending，D对pending材料事实阻断，且D不修改事实 | 明确由谁核对、更新状态、保存审计并再次校验，不能仅因抽取成功或用户确认就标记supported |
| 完整性policy | 本轮采用D演示配置，并非生产规则 | A/B/D/E确认必填字段、材料要求和严重性；不能把演示policy直接当团队决议 |

## 尚未完成

未执行新的在线Dify、真实OCR、后端事务或前端流程；未完成A生成草稿到D确认/导出校验的完整链路。现有草稿门槛、共享Schema、D源码均未修改。

因此当前可报告“首轮离线接口检查通过，业务流程待对齐”，不能报告“A/D全部联调完成”。D回传包附检查脚本、四份合成ValidationRequest、结果和反馈说明，供双方复核；脚本应放到含agent/、contracts/、validation/的完整测试项目根目录运行。
