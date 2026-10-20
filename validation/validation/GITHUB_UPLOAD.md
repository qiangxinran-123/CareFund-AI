# D 模块 GitHub 上传说明

当前为 2026-10-20 的 INT-07/INT-08 修订。先读 `CURRENT_STATUS.md` 和 `INT07_INT08_HANDOFF.md`。

1. GitHub 团队仓库切换到自己的 `feature/validation` 分支。
2. 在仓库根目录选择 Add file → Upload files，将解压后的整个 `validation` 文件夹拖入上传区。
3. 检查待提交路径全部以 `validation/` 开头，不上传 ZIP 本身，也不要在 `validation/` 内再套同名目录。
4. 提交说明建议 `fix: finalize demo validation policy and draft severity gates`，然后创建到 main 的 PR，由非作者审查。

本包仅包含 D 目录，排除虚拟环境、缓存、密钥、数据库、真实患者 CSV 和其他成员顶层源码。测试中的 A 源码只位于 `validation/tests/fixtures/`，不会覆盖根目录 `agent/`。运行测试时使用团队仓库既有的 `contracts/` 和实际 A/B 模块。

```powershell
python -m pip install -r validation/requirements.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-results
# 可选后端适配测试：
python -m pip install -r validation/requirements-integration.txt
python -B -m validation.tools.verify_int07_int08 --output local-int-backend-results --with-backend
```

预期分别为 129 项契约/D 测试；可选分进程运行 D 后端适配 5 项和 B 原有 11 项。合成门禁结果见 `verification/int07_int08/`，无 API 调用。测试通过不替代 A/B 对接确认与真实系统验收。
