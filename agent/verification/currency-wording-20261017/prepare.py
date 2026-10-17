"""Prepare six synthetic regressions and local prompt candidates; no API."""
import copy
import hashlib
import json
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[2]
sys.path.insert(0,str(ROOT))
from agent.agent_service import AgentService
from agent.currency_review import currency_review_flags
from agent.build_workflows import WORDING_RULE

RULE='未提供平台规则或币种信息时，不得臆测平台常用、默认、支持或接受哪些币种。明确的外币金额按原币种和原金额保留，禁止无依据换算；币种不明时保留原文并询问币种，不添加平台偏好。用户自述的平台规则只能标明为用户自述，不能当作已核实的正式规则。'
PRIVATE=ROOT/'agent/.local/currency-wording-20261017'
def sha(raw):return hashlib.sha256(raw).hexdigest()
def write(p,data):
    assert not p.exists()
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

if __name__=='__main__':
    assert not PRIVATE.exists(); PRIVATE.mkdir(parents=True)
    previous=json.loads((ROOT/'agent/.local/expanded-20261017/suite.json').read_bytes())
    old=next(c for c in previous['cases'] if c['case_id']=='expand_synthetic_extract_007')
    cases=[copy.deepcopy(old)];cases[0]['case_id']='currency_original_usd'
    examples=[
        ('currency_exact_cny','已支付医疗费人民币389.17元，未提供后续预估费。',
         {'money_exact':{'treatment.paid_cost':[{'currency':'CNY','amount_minor':38917}]},'no_estimate_money':True}),
        ('currency_ambiguous_symbol','已支付医疗费写作 $7200，未说明是哪种币种，请不要推定币种或换算。',
         {'no_medical_money':True,'allow_ambiguous_cost_text':True,'must_question':True}),
        ('currency_exact_eur','已支付医疗费 EUR 18.29，明确为欧元，未提供后续预估费。',
         {'no_estimate_money':True}),
        ('currency_user_rule_claim','已支付医疗费 USD 389.17。我听说“平台只接受人民币”，但这只是我的猜测，没有正式规则，也不知道是否属实，请勿据此换算。',
         {'currency_guard':'USD','expected_foreign_amount_minor':38917,'no_estimate_money':True}),
        ('currency_negated_rule','已支付医疗费 USD 389.17。不能推断平台常用人民币；没有提供平台币种规则，请原币种保留，勿换算。',
         {'currency_guard':'USD','expected_foreign_amount_minor':38917,'no_estimate_money':True})]
    for identifier,text,expected in examples:
        cases.append(dict(case_id=identifier,operation='extract',data_class='synthetic',group=identifier,
            request=dict(schema_version='1.0',application_id='app_'+identifier,application_revision=1,
                user_input={'description':'以下为完全虚构测试，不对应真实患者。'+text},
                extracted_documents=[],candidate_facts=[]),expectation=expected))
    for c in cases:AgentService(None).validate(c['request'],'AgentExtractRequest')
    write(PRIVATE/'suite.json',{'cases':cases})
    old_row=next(r for r in json.loads((ROOT/'agent/verification/expanded-20261017/summary.json').read_bytes())['cases'] if r['case_id']==old['case_id'])
    raw=(ROOT/old_row['response_file']).read_bytes();assert sha(raw)==old_row['response_sha256']
    flags=currency_review_flags(json.loads(raw));assert flags
    source=ROOT/'agent/workflow.deepseek-extract.yml';body=source.read_bytes()
    anchor=(WORDING_RULE+"'").encode();assert body.count(anchor)==1
    assert "'" not in RULE
    candidate=body.replace(anchor,(WORDING_RULE+'\n\n            8. '+RULE+"'").encode())
    target=ROOT/'agent/workflow.deepseek-extract.currency-v3-candidate.yml'
    assert not target.exists();target.write_bytes(candidate)
    assert candidate.replace(('\n\n            8. '+RULE).encode(),b'')==body
    prompt=ROOT/'agent/prompts/extract-currency-v3.md';assert not prompt.exists()
    prompt.write_text((ROOT/'agent/prompts/extract-v2.md').read_text(encoding='utf-8').rstrip()+'\n\n'+RULE+'\n',encoding='utf-8')
    write(HERE/'preparation.json',dict(planned_calls=6,data_class='synthetic_only',new_API_calls=0,
        suite_file=(PRIVATE/'suite.json').relative_to(ROOT).as_posix(),suite_sha256=sha((PRIVATE/'suite.json').read_bytes()),
        historical_request_preserved=cases[0]['request']==old['request'],historical_response_sha256=sha(raw),
        historical_error_now_marked_for_review=flags,source_DSL_sha256=sha(body),candidate_DSL_sha256=sha(candidate),
        candidate_DSL_is_not_online_export=True,prompt_rule=RULE,
        publication_evidence='User reported published; editor and export not independently inspected because UI automation blocked.',
        generated_cases=[c['case_id'] for c in cases],automatic_history_unchanged=True))
    print(json.dumps({'prepared_cases':len(cases),'historical_error_detected':True,'new_API_calls':0}))
