"""Offline replay requires ignored inputs/responses; never calls a model."""
import importlib.util
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('expanded_final_check',HERE/'finalize.py')
CHECK=importlib.util.module_from_spec(spec);spec.loader.exec_module(CHECK)
if __name__=='__main__':
    path=HERE/'summary.json'
    if not path.is_file():raise SystemExit('Public summary unavailable; no replay performed.')
    accepted,checks=CHECK.verified_records(CHECK.parse_object(path.read_bytes()))
    print(json.dumps({'offline_recheck':checks,'accepted_or_reviewed':len(accepted),'new_model_calls':0,'patient_text_printed':False}))
