"""Offline replay only; no Dify runner invocation."""
import importlib.util
import json
from pathlib import Path
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('currency_final_recheck',HERE/'finalize.py')
CHECK=importlib.util.module_from_spec(spec);spec.loader.exec_module(CHECK)
if __name__=='__main__':
    report=json.loads((HERE/'summary.json').read_bytes())
    accepted=CHECK.verify(report)
    print(json.dumps(dict(offline_rechecked=len(report['cases']),accepted_after_context_review=len(accepted),new_model_calls=0)))
