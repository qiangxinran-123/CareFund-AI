"""Build the fixed A-only delivery using the existing private-evidence audit.

Run on the original workstation only. The recipient runs verify_saved.py.
Neither builder sends data, changes Git, or resumes the batch.
"""
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    source = HERE.parent / 'content-review-20261017' / 'build_delivery.py'
    spec = importlib.util.spec_from_file_location('carefund_review_delivery_builder', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.HERE = HERE
    builder.ARCHIVE = ROOT.parent / 'deliveries' / 'CareFund-A-code-and-results-20261017-fixed.zip'
    receive = '''# CareFund A 模块：修复后代码与测试结果（2026-10-17）

先阅读 agent/CURRENT_HANDOFF.md，再看 agent/verification/content-fix-20261017/README.md。

本包仅更新 agent/，沿用小组仓库 contracts/schemas/；先解压到独立目录审阅，再比较合入。没有队友其他模块、真实医疗输入或响应、CSV、密钥、.local/ 或虚拟环境。

本次已处理上一轮发现的提醒推测、追问质量和草稿引述指令问题。B 须调用 AgentService.extract/draft，直接调用 DifyRunner 或 Dify 网页不会应用本次代码策略。不需要为本次代码修复重新发布 Dify；正式 DSL 为 workflow.deepseek-extract.yml 及 workflow.deepseek-draft.yml。

在已有小组仓库根目录执行：

1. python -m pip install -r agent/requirements.txt
2. python -m unittest discover -s agent/tests（108 项离线测试）。
3. python agent/verification/content-fix-20261017/verify_saved.py（21 份虚构抽取、5 份正常草稿、1 份按预期拦截的草稿，0 次 API 调用）。

已在原机回放 60 条真实来源与 27 份虚构结果，覆盖原 20 个带发现案例；全部 1,341 份可解析批量保存响应中，1,339 份通过且事实不变，2 份历史非法响应仍拒绝。原文和旧错误未改写。固定提醒与有界指令拦截不代表医疗准确率或全系统验收。

旧 content-review 报告保留当时未修复状态，本次状态以 CURRENT_HANDOFF 和 content-fix 报告为准。完整 CSV 原批次冻结，未自动继续；本次新增生成调用为 0。

PACKAGE_MANIFEST.json 列出本包文件 SHA-256 与共享契约指纹。交付 ZIP 的独立解压复验结果放在 ZIP 旁的 .verified.json 中。本次未上传 GitHub。
'''.encode('utf-8')
    builder.main(receive_readme=receive)


if __name__ == '__main__':
    main()
