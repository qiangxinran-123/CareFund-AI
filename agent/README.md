# CareFund-AI Agent

Agent 模块封装 Dify 工作流和模型输出边界，负责候选事实抽取、补充问题和受事实约束的草稿生成。它不维护申请状态，不决定最终导出，也不能把模型返回值当作审核结论。

## 安全边界

- 所有请求和响应使用 `contracts/schemas/agent.schema.json` 校验。
- 响应必须保持 application ID 与 revision 一致。
- 已有事实必须原样保留；修订生成新候选，不允许原 ID 静默改写。
- 新候选只能是 `pending` 且未确认，Evidence ID 必须来自输入。
- 新事实和追问字段受 `extract_policy.py` 白名单限制。
- 草稿只接收已确认、非冲突、非 unsupported 的事实。
- blocking Validation issue 会在模型调用前拒绝；info/warning 完整保留，但不发送给草稿模型。
- 草稿必须逐条引用并完整保留事实原值、来源和不确定性。

正式业务门禁见 [`docs/VALIDATION_POLICY.md`](../docs/VALIDATION_POLICY.md)。模型成功返回不等于可以确认或导出，后端仍会执行当前 revision 的确定性复核。

## 配置

```text
DIFY_BASE_URL=https://api.dify.ai/v1
DIFY_EXTRACT_API_KEY=<抽取工作流密钥>
DIFY_DRAFT_API_KEY=<草稿工作流密钥>
```

抽取与草稿使用不同应用密钥。密钥只存在于后端进程环境，不写入浏览器变量、日志、测试报告或仓库。网络调用默认无自动重试、无静默 Mock 降级；超时后应先查询服务端执行记录。

当前正式工作流文件：

- `workflow.deepseek-extract.yml`
- `workflow.deepseek-draft.yml`

## 调用

```python
from agent.agent_service import AgentService
from agent.dify_runner import DifyRunner

service = AgentService(DifyRunner.from_env(user=application_id))
extract_response = service.extract(extract_request)
draft_response = service.draft(draft_request, validation_result=validation_result)
```

后端在异步路由中通过线程池执行同步 Agent 调用，并在保存结果前再次检查 application revision。

## 测试

```powershell
& backend/.venv/Scripts/python.exe -m pytest agent/tests contracts/tests -q
```

测试覆盖 Schema、证据引用、字段范围、状态自证、提示注入、金额与币种、草稿遗漏/扩写、异常脱敏和 Validation 严重性门禁。测试样例均为虚构数据。
