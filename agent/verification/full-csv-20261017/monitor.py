"""Local observer: review saved outputs and export coverage; never calls a model."""
import argparse
import json
import time

from prepare import HERE
from export_status import main as export_status
from review_saved import main as review_saved
from report_guard_live import main as guard_report


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--question-report-only', action='store_true')
    args = parser.parse_args()
    while True:
        progress = json.loads((HERE / 'live-progress.json').read_bytes())
        if not args.question_report_only:
            review_saved(stop_on_finding=True)
            export_status()
        guard_report()
        # A final pass follows runner completion; no credential, retry or restart path.
        if progress['status'] != 'running':
            print(json.dumps({'monitor': 'finished', 'runner_status': progress['status']}), flush=True)
            break
        time.sleep(20)
