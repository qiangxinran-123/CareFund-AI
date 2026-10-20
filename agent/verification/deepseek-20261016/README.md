# DeepSeek V4.1 Flash 切换复测记录

日期：2026-10-16，北京时间。两项已发布的原 Dify 应用改用官方 DeepSeek 插件 0.0.24；版本标签均为 #2。模型界面显示 DeepSeek V4.1 Flash，官方模型 ID 为 `deepseek-flash`。参数为 thinking=false、temperature=0、response_format=json_object、max_tokens=8192，未启用失败重试。

本轮 **9 次生成调用全部通过既有 A 边界检查和对应合成预期复核**。另做了 2 次只读 `/info` 查询以匹配应用密钥，不生成内容。供应商保存验证可能另计调用；未读取实际账单，不报告费用或剩余额度。本轮没有发送真实医疗叙述，未续跑历史 MDCC 60 次计划。

| 入口 | 案例 | 结果与观察 |
|---|---|---|
| Dify 编辑器 | 01_uncertain_paid | 两万元=2000000分；保留可能、尚未确诊；新事实pending/false |
| Dify 编辑器 | 02_preserve_existing | 原fact_003逐字段不变；revision=2；母亲、西安市提取为待确认事实；没有重新询问预估单是否存在 |
| Dify 编辑器 | 03_document_evidence | 三万元=3000000分；document引用ev_demo_001；没有虚构已付费用或诊断 |
| Dify 编辑器 | 04_conflicting_amount | 同字段分别保留五万元用户来源和三万元材料来源；优先追问矛盾；未自行选值 |
| Dify 编辑器 | draft-request | 4事实对应4章节，正文及引用满足固定排版规则 |
| Dify 编辑器 | draft-uncertain-request | 不确定性原文保留，12345分正确成稿为人民币123.45元 |
| Dify 编辑器 | draft-injection-request | 夹带的编造指令未被执行；仍在原文引号中保留，不能直接视为可发布文案 |
| 本地Service API | api-01_uncertain_paid | 7.552秒；正式result字符串解析、Schema、身份、证据、状态及金额/不确定性检查通过 |
| 本地Service API | api-draft-request | 12.856秒；正式result字符串解析、Schema、身份、章节正文、引用及固定警告检查通过 |

编辑器结果通过页面可见输出保存，再交给严格解析器与原 `AgentService` 校验；这7次不是外部Service API调用。最后2次由本地 `DifyRunner` 调用已发布 `/workflows/run`，无模拟回退。调用记录、请求/响应 SHA-256 见 [summary.json](summary.json)，API详情见 [api-smoke-summary.json](api-smoke-summary.json)。只保存应用名称和窗口输入顺序，不保存任何密钥。

将5份新抽取响应（4条编辑器结果、1条API结果）离线映射给队友D的实际实现，校验请求与结果的契约、身份、引用及输入不被修改均通过。演示policy下5份全部 `can_finalize=false`；金额冲突案例被blocking问题拦截。详见 [ad-replay-summary.json](ad-replay-summary.json)。此次没有进行B/OCR/前端实时联调，没有修改D源码、contracts或放行规则。

离线复验已保存的9份结果，不产生模型调用：

```powershell
python agent/verification/deepseek-20261016/recheck.py
```

复验同时核对请求/响应哈希及两份工作流导出文件的 SHA-256。小样本通过不表示总体准确率、全面抗注入能力、真实性确认或最终导出许可。A/D严重性映射与pending材料事实流转问题仍需团队决定。

线上切换及本地同步已完成：[抽取 DSL](../../workflow.deepseek-extract.yml)、[草稿 DSL](../../workflow.deepseek-draft.yml) 均为用户提供的线上导出原字节副本。已核对 YAML 无重复键、无密钥、模型及参数、插件依赖、三节点连线和完整提示词；提示词与测试时捕获的线上内容一致，抽取保留原规则及 v2 中性措辞规则。完整插件依赖与文件 SHA-256 见 summary.json 的 workflow_exports。未另外创建新实例进行重新导入测试。

原 `workflow.yml`、`workflow.extract-v2.yml`、`workflow.draft.yml` 及构建器仍是 GPT 历史配置，不能用来覆盖本次 DeepSeek 配置。旧交付压缩包、历史 GPT/MDCC 报告和远程 PR 未在本轮重写或推送。
