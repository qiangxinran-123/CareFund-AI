# fix: finalize demo validation policy and draft severity gates

落实 INT-07 与 INT-08 的 D 侧：提供 demo_v1 和明确的严重性/阻断 ID 映射，info/warning 保留展示且不单独阻止草稿；冲突、无效引用、未确认事实与过期版本继续阻断。

只修改 `validation/`。新增命名 Policy 加载、建议项 warning、生成前当前版本检查，以及与确认/导出一致的事实门禁；demo_v1 最终草稿要求完整保留 A 当前逐事实原值和来源。旧配置默认保留全 ID 行为，不静默改变历史调用。A/B/C 和公共契约均未修改。

## 验证

```powershell
python -B -m validation.tools.verify_int07_int08 --output local-int-results --with-backend
python -B -m unittest discover -s agent/tests -q
```

契约/D 129 项、D 后端适配 5 项、B 原有 11 项、A 原有 108 项测试通过。六组门禁案例覆盖正常、info、warning、金额冲突、旧 revision 和无效引用；另有不存在 fact_id、确认时间、未确认可选事实及自由文案篡改回归。只用合成输入与离线 runner，模型调用 0 次。

详细规则和接入示例见 `INT07_INT08_HANDOFF.md`，实际日志见 `verification/int07_int08/`。A/B 需确认草稿请求只传阻断 ID 的约定；B 将 Policy 路径改为 `validation/policies/demo_v1.json`，并接入 D 映射、保留完整提示给前端。

B 原有全 ID 转发仍会误阻断 info，测试明确记录该现象；本 PR 没有越界修改 B。尚未完成人工 A/B 确认及在线系统/事务验收，不宣称全链路问题已关闭。
