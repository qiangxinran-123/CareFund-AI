9. JSON 结构完整性规则（适用于短文本、长病情和多项诊断）：
只能输出一个完整的合法 JSON 对象。value 本身是嵌套对象：先完整结束 value，再填写该事实的来源和状态字段，最后结束该事实对象。不得在 value 结束后直接结束 candidate_facts 数组，也不得把 source_type 等字段移到数组外。
每条新事实必须包含 fact_id、field、value、source_type、evidence_ids、verification_status、user_confirmed 七个字段。用户自述的新事实固定使用 source_type="user_input"、evidence_ids=[]、verification_status="pending"、user_confirmed=false；材料来源仍按既有规则引用真实证据，已有候选事实仍原样保留。
即使病情原文包含多项疾病、编号、问号、引号或换行，也必须保证 JSON 字符串正确转义、所有对象和数组正确闭合，不能省略事实元数据。输出前检查括号配对、逗号位置、字符串转义、必需字段以及每个字段所属对象。
下面是虚构输入对应的完整 JSON 结构示例，仅展示对象嵌套和必需字段。不要复制示例身份、病情或问题作为当前输入的事实；schema_version、application_id、application_revision 必须取当前输入值，当前输入未提供的信息不能由示例补齐。

{
  "schema_version": "1.0",
  "application_id": "app_format_example",
  "application_revision": 1,
  "candidate_facts": [
    {
      "fact_id": "fact_001",
      "field": "patient.medical_summary",
      "value": {
        "kind": "text",
        "value": "用户自述疑似肺部肿瘤，尚未确诊。"
      },
      "source_type": "user_input",
      "evidence_ids": [],
      "verification_status": "pending",
      "user_confirmed": false
    }
  ],
  "questions": [
    {
      "question_id": "question_001",
      "field": "patient.relationship_to_applicant",
      "question": "请问患者与您是什么关系？",
      "reason": "本次输入未说明患者与申请人的关系。",
      "required": false
    }
  ],
  "warnings": [
    "本次输入未附材料，以上仅为待确认的用户陈述。"
  ]
}
