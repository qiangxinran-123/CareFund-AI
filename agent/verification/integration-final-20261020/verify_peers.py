"""Run optional offline tests against B/D, without modifying their sources."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--team-root', type=Path, required=True)
    args = parser.parse_args()
    sys.path.insert(0, str(args.team_root.resolve()))
    sys.path.insert(0, str(ROOT))
    # Load the local A first; B and D are supplied by the peer checkout.
    from agent.agent_service import AgentService
    spec = importlib.util.spec_from_file_location('carefund_a_peer_tests', HERE / 'test_peer_integration.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    print(json.dumps(dict(tests=result.testsRun, passed=result.wasSuccessful(), new_model_calls=0,
                          scope='Real B/D adapters, synthetic fixtures, mocked generation transport; not a live end-to-end run.')))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
