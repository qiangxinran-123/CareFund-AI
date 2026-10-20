# D 模块当前联调交付状态

更新日期：2026-10-20（Asia/Shanghai）。基于 `CareFund-AI-main (2).zip` 和最终联调任务说明，只修改 `validation/`，工作分支为本地 `feature/validation`，未提交/推送/创建 PR。

## 本轮已完成

- INT-07：提供命名演示规则 `validation/policies/demo_v1.json`。沿用 B 原 integration policy 的病情说明、材料支持的后续费用预估、已解析附件和事实确认要求；不擅自取消必填内容。对关系、城市、日期和病情自述的材料来源设置非阻断建议。未确诊时允许保留检查进展和不确定性。
- INT-08 的 D 侧：显式约定 `draft_issue_scope=blocking`，A 草稿请求只接收阻断 ID，完整 `ValidationResult.issues` 保留所有提示供前端和审计使用；旧配置默认仍保留 all-ID 行为。
- 新增 `validate_for_generation()` 检查当前申请及生成请求版本，生成、确认和导出均核对事实确认、冲突和引用；demo_v1 最终草稿按 A 当前逐事实格式严格核验，不以数字没变为由放过新编写的医疗经历。

规则仅适用于本次演示，不代表平台官方审批标准。严重性表、门禁表及 B 最小接入示例见 `INT07_INT08_HANDOFF.md`。

## 实际测试

| 范围 | 结果 |
| --- | --- |
| 契约与 D 回归 | 129 项通过（原 110 + 新增 19） |
| D 的真实 B 适配器测试 | 5 项通过 |
| B 原有测试 | 11 项通过，API 场景为原有 Mock 模式 |
| A 原有离线测试 | 108 项通过 |
| 六组合成门禁案例 | 正常、info、warning 允许；冲突、旧版本、无效引用阻断 |
| 模型 API 新调用 | 0 次 |

日志和实际输入输出位于 `verification/int07_int08/`。A 的测试最初受沙箱临时目录权限阻止，放开该限制后 108 项通过。B API 测试在导入时配置 Mock 单例，验证脚本将其与 D 真实适配器测试分进程运行，避免导入顺序共享 Real 单例。

```powershell
python -m pip install -r validation/requirements.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-results
# 可选后端适配回归：
python -m pip install -r validation/requirements-integration.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-backend-results --with-backend
```

## 对接方仍需完成

1. A/B 确认阻断 ID 与完整提示列表的约定；尚未取得人工确认，不冒充团队决议。
2. B 加载 demo_v1 并接入 D 的生成映射。B 当前全 ID 转发仍会让 A 拒绝 info，测试已复现；只更改配置路径还不能完成系统修复。
3. B/C/E 验证事务、持久化、用户确认操作、在线 OCR/Dify、提示展示和最终下载。

未修改 A/B/C 或公共契约，没有承担上传幂等、数据库或其他成员任务。旧的 10 月 16/18 日记录只作为历史证据保留，当前规则以本页及 INT07_INT08_HANDOFF 为准。
