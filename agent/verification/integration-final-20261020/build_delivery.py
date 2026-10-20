"""Build an A-only final-integration ZIP with the existing private-data audit."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verified-live', action='store_true', help='Append a new delivery with the completed real-call evidence')
    args = parser.parse_args()
    checks = json.loads((HERE / 'local-checks.json').read_bytes())
    assert all(test['passed'] for test in checks['tests'])
    if args.verified_live:
        live = json.loads((HERE / 'live-results.json').read_bytes())
        assert live['status'] == 'two_real_calls_passed' and live['calls_attempted'] == 2 and live['automatic_retries'] == 0
    source = HERE.parent / 'content-review-20261017/build_delivery.py'
    spec = importlib.util.spec_from_file_location('carefund_a_delivery_audit', source)
    builder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(builder)
    builder.HERE = HERE / 'live-delivery' if args.verified_live else HERE
    builder.HERE.mkdir(exist_ok=True)
    filename = 'CareFund-A-final-integration-20261020-live-verified.zip' if args.verified_live else 'CareFund-A-final-integration-20261020.zip'
    builder.ARCHIVE = ROOT.parent / 'deliveries' / filename
    readme = '''# CareFund A 最终联调交付（2026-10-20）

先读 agent/CURRENT_HANDOFF.md 和 agent/FINAL_INTEGRATION_HANDOFF.md。

本包仅含 agent/，供比较合入小组仓库。公共 contracts/schemas/ 沿用小组现有版本；其他成员目录、密钥、真实患者原文与响应、完整 CSV、.local/ 和虚拟环境不在包内。

核心修改：A 可配对完整同版本 D 结果，允许 info/非阻断 warning，继续拒绝 blocking、未确认事实、冲突及不匹配引用；完整问题保留，只对发送给模型的 ID 采用 D 明确规定的 blocking 投影。另补充安全异常分类、B 同步/后台调用约定与最多两次合成真实 API 复测工具。不需要再手动改 Dify 提示词，不修改 JSON 契约。

离线：A 132、契约 10、A/B/D 专项 9 项通过；B 原有 11 项及经规范化隔离副本运行的 D 119 项通过。D 原仓库目录和夹具问题请先读交接文档，不应把测试副本的通过理解为原仓库直接可运行。

真实调用状态与时间单独保存在 agent/verification/integration-final-20261020/ 下；没有实际成功记录就不能声称当前 API 已验收。旧批次和回放记录均是历史证据，未重写失败结果。完整 CSV 不会因本包自动续跑。

复验：安装 agent/requirements.txt，在包含正式 contracts 的小组仓库根目录运行 python -m unittest discover -s agent/tests。可选 B/D 专项运行方法见最终交接文档。

PACKAGE_MANIFEST.json 为包内文件指纹；ZIP 的独立解压检查结果在同名 .verified.json 中。
'''.encode()
    if args.verified_live:
        readme += '''
本包后续证据：2026-10-20 北京时间21:21完成2次真实生成，抽取3.952秒、草稿4.117秒，均经B进程内适配器→A→Dify，0次重试。完整6条非阻断提示保留；合成响应及时间见agent/verification/integration-final-20261020/live-results.json。live-status.json是输入前的历史快照，不能作为当前状态。未执行网页/OCR/HTTP后台任务的完整验收，本次未新增其他生成调用。
'''.encode()
    builder.main(receive_readme=readme)


if __name__ == '__main__':
    main()
