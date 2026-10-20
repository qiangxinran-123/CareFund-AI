
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
=======
# D 模块上传 GitHub

本文件随 `validation/` 上传。上传包顶层只有这个模块，不包含项目根的 `agent/`、`contracts/`、其他成员目录、虚拟环境、缓存、密钥或 Git 历史。测试中的 A 源码位于 `validation/tests/fixtures/`，仅作为有原始指纹的离线测试夹具，不会覆盖根目录 `agent/`。

## 网页上传步骤

1. 打开团队 GitHub 仓库，切换到 `feature/validation` 分支。如果不存在，从团队当前确认的基线创建该分支。
2. 回到仓库根目录（能看到 `agent/`、`backend/`、`validation/` 的位置），选择 **Add file → Upload files**。
3. 解压 `CareFund-D-GitHub-20261018.zip`，将解压得到的整个 **validation 文件夹**拖入上传区。不要上传 ZIP 本身，也不要在 GitHub 的 `validation/` 内再次上传同名文件夹。
4. 检查待提交的每条路径都以 `validation/` 开头。提交说明可用 `feat: implement fact validation and agent integration`，提交到自己的功能分支。
5. 创建 `feature/validation → main` 的 Pull Request，描述可参考 `validation/PR_DESCRIPTION.md`，交由非作者成员审查后合并。

在已有本地团队仓库操作时，将包内 `validation/` 合入对应目录，先检查 `git status` 和实际 diff，再只暂存本次 D 的文件。不要用本地 ZIP 初始化产生的无共同历史分支直接覆盖远程仓库。

## 包内内容

核心规则、A/D 适配入口、依赖说明、全部 100 项 D/适配测试及其合成夹具都保留。另有团队原有的 10 项契约测试，应在已有项目的 `contracts/` 中运行，上传包不携带或改动公共契约。

最新逐案例输入和输出在上传版中集中保存于 `validation/verification/a_20261018/case-results.json`；对象键保留原始文件名，值为原始 JSON 内容。`summary.json` 保留本轮统计，旧交接结果仍在历史目录。此整理只减少文件数量，不删掉案例内容，也不改变运行逻辑。回放脚本仍能重新生成逐案例文件。

实际验证结果、未完成的业务规则和接口门槛见 `validation/CURRENT_STATUS.md`。本包只交付 D 模块，不表示真实 OCR、后端事务或在线全链路已验收。

## 上传后验证

在已有完整团队仓库根目录执行：

```powershell
python -m pip install -r validation/requirements.txt
python -B -m unittest contracts.tests.test_contracts validation.tests.test_validation validation.tests.test_agent_adapter validation.tests.test_latest_agent -q
python -B -m validation.tools.replay_latest_a --output local-replay-results
```

预期 110 项测试通过；最新合成回放为 21 个抽取、5 个正常草稿和 1 个按预期阻断的指令草稿，无 API 调用。运行时需要保留团队的共享 `contracts/schemas/`。
