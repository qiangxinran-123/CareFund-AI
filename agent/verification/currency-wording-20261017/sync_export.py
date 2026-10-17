"""Verify a user-supplied DSL, archive the old bytes and sync the new export.

Local tool dependency only: agent/.local/yaml-validation-deps/PyYAML.
Never imports, publishes or invokes a Dify app.
"""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT/'agent/.local/yaml-validation-deps'))
import yaml
spec=importlib.util.spec_from_file_location('currency_prompt_preparation',HERE/'prepare.py')
PREP=importlib.util.module_from_spec(spec);spec.loader.exec_module(PREP)

class UniqueSafeLoader(yaml.SafeLoader):pass
def mapping(loader,node,deep=False):
    result={}
    for k,v in node.value:
        key=loader.construct_object(k,deep=deep)
        if key in result:raise ValueError('Duplicate YAML key')
        result[key]=loader.construct_object(v,deep=deep)
    return result
UniqueSafeLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,mapping)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def norm(text):return re.sub(r'\s+','',text)
def ignore_selection(value):
    if isinstance(value,dict):return {k:ignore_selection(v) for k,v in value.items() if k!='selected'}
    if isinstance(value,list):return [ignore_selection(v) for v in value]
    return value
def system(workflow):
    llms=[n for n in workflow['workflow']['graph']['nodes'] if n['data']['type']=='llm']
    assert len(llms)==1
    prompts=[p for p in llms[0]['data']['prompt_template'] if p['role']=='system'];assert len(prompts)==1
    return llms[0],prompts[0]

if __name__=='__main__':
    source=Path(sys.argv[1]);target=ROOT/'agent/workflow.deepseek-extract.yml'
    profile=json.loads((HERE/'preparation.json').read_bytes())
    old_raw=target.read_bytes();new_raw=source.read_bytes()
    assert sha(old_raw)==profile['source_DSL_sha256']
    assert not re.search(rb'(?:app-|sk-)[A-Za-z0-9_-]{20,}',new_raw)
    old=yaml.load(old_raw,Loader=UniqueSafeLoader);new=yaml.load(new_raw,Loader=UniqueSafeLoader)
    assert new['app']['name']=='CareFund-信息抽取与追问-修订版'
    assert not new['workflow']['environment_variables'] and not new['workflow']['conversation_variables']
    old_node,old_prompt=system(old);new_node,new_prompt=system(new)
    assert norm(new_prompt['text'])==norm(old_prompt['text'])+'8.'+norm(PREP.RULE)
    assert new_node['data']['model']==old_node['data']['model']
    assert new_node['data']['model']['name']=='deepseek-flash'
    comparable=copy.deepcopy(new);system(comparable)[1]['text']=old_prompt['text']
    assert ignore_selection(comparable)==ignore_selection(old)
    # Compare the earlier local candidate semantically, allowing formatting and UI selection.
    candidate=yaml.load((ROOT/'agent/workflow.deepseek-extract.currency-v3-candidate.yml').read_bytes(),Loader=UniqueSafeLoader)
    candidate_prompt=system(candidate)[1]
    assert norm(candidate_prompt['text'])==norm(new_prompt['text'])
    candidate_prompt['text']=new_prompt['text']
    assert ignore_selection(candidate)==ignore_selection(new)
    archived=HERE/'pre-currency-extract-export.yml';assert not archived.exists();archived.write_bytes(old_raw)
    target.write_bytes(new_raw);assert target.read_bytes()==new_raw
    prompt_target=ROOT/'agent/prompts/extract-currency-v3.md'
    # Keep the exact exported prompt as authoritative; the initial preparation held the appended rule candidate.
    prompt_target.write_text(new_prompt['text']+'\n',encoding='utf-8')
    report=dict(date='2026-10-17',source_filename=source.name,source_bytes=len(new_raw),
        old_export_archived=archived.relative_to(ROOT).as_posix(),old_export_sha256=sha(old_raw),new_export_sha256=sha(new_raw),
        synced_file=target.relative_to(ROOT).as_posix(),synced_as_original_bytes=True,
        exact_exported_SYSTEM_prompt_file=prompt_target.relative_to(ROOT).as_posix(),
        exact_exported_SYSTEM_prompt_sha256=sha(new_prompt['text'].encode()),
        model=new_node['data']['model'],dependencies=new['dependencies'],
        normalized_prompt_only_adds_rule_8=True,all_non_prompt_execution_configuration_unchanged=True,
        local_candidate_semantically_matches_actual_export=True,UI_selection_difference_ignored=True,
        credentials_pattern_scan='passed',published_version_label='not independently observed',
        source_and_limit='User supplied editor export plus user publication confirmation and six real API regressions; export alone does not prove the published version.',
        yaml_parser_version=yaml.__version__,new_model_calls=0)
    p=HERE/'dsl-verification.json';assert not p.exists();p.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'new_export_sha256':report['new_export_sha256'],'only_execution_change':'append currency wording rule',
        'model_and_parameters_unchanged':True,'synced_as_original_bytes':True,'new_model_calls':0}))
