# CareFund-AI Validation

Validation 是不依赖大模型判断的确定性安全层。它接收正式 `ValidationRequest`，输出 `ValidationResult`，不修改原始事实、用户确认、申请状态或数据库。

## 正式规则

提交版本使用 `validation/policies/carefund_v1.json`，与后端 `validation-policy.v1.json` 保持一致。规则说明见 [`docs/VALIDATION_POLICY.md`](../docs/VALIDATION_POLICY.md)。未提供 Policy 时会产生 blocking 问题，禁止生成、确认和导出。

Policy 要点：

- 病情自述和预计治疗费用必填。
- 预计费用需要材料 Evidence，且至少一份材料已完成解析。
- 必填事实需要用户确认。
- 同字段不同值、金额/日期冲突、悬空或跨申请引用、无材料支持、提示注入均阻断。
- 用户陈述来源产生 info；建议字段或建议材料产生 warning，允许继续但完整保留。

## 校验范围

- JSON Schema、枚举、日期、整数最小货币单位和字段类型。
- `Fact -> Evidence -> UploadedDocument` 引用完整性。
- 材料文字是否明确支持文本、金额、日期及已支付/预计费用语义。
- 草稿是否完整保留事实原值、来源和不确定性，是否新增无依据内容。
- 生成、确认、导出时的申请 ID、revision、草稿状态和确认时间。

`supported` 仅表示当前材料文字支持事实，不代表材料真伪认证；`can_finalize` 也不代表医疗诊断或筹款平台审核通过。

## Python 接口

```python
from validation import (
    load_policy,
    validate,
    validate_for_confirmation,
    validate_for_export,
)

policy = load_policy("carefund_v1")
analysis = validate(validation_request, policy=policy)
confirmation = validate_for_confirmation(
    validation_request, application, draft, confirmation_request, policy=policy,
)
export = validate_for_export(
    validation_request, application, draft, export_request, policy=policy,
)
```

Application、Draft 和操作请求必须来自后端当前存储快照。后端负责在事务或等价锁中复查 revision 并执行状态转换。

## CLI

```powershell
& backend/.venv/Scripts/python.exe -m validation validation/examples/request.demo.json --policy carefund_v1
```

退出码：`0` 允许继续，`1` 存在 blocking，`2` 输入、Policy 或文件非法。标准输出为 JSON，错误不会回显患者原文或密钥。

## 测试

```powershell
& backend/.venv/Scripts/python.exe -m pytest validation/tests validation/integration_tests contracts/tests -q
```

测试使用虚构数据，覆盖正常流程、warning/info、缺失字段、冲突、非法引用、旧 revision、确认和导出门禁。
