"""Evaluation blind-spot regression; no API and no clinical assertions."""
import copy
import unittest
from agent.currency_review import currency_review_flags, PLATFORM_CURRENCY_FLAG


class CurrencyReviewTests(unittest.TestCase):
    def test_unsupported_default_claim_variants_request_review(self):
        for text in ('币种与平台常用的人民币不同', '平台默认币种为CNY',
                     '平台通常支持美元', '平台只接受人民币', '平台惯用货币是 EUR'):
            with self.subTest(text=text):
                self.assertEqual(currency_review_flags({'warnings':[text]}), [PLATFORM_CURRENCY_FLAG])

    def test_neutral_currency_preservation_does_not_request_review(self):
        self.assertEqual(currency_review_flags({'warnings':['按用户自述保留 USD 389.17，未换算，尚待材料核对。']}), [])

    def test_question_and_reason_are_both_reviewed(self):
        for key in ('question','reason'):
            self.assertEqual(currency_review_flags({'questions':[{key:'平台只接受人民币，请换算。'}]}), [PLATFORM_CURRENCY_FLAG])

    def test_explicit_attribution_is_review_candidate_not_automatic_failure(self):
        self.assertEqual(currency_review_flags({'warnings':['用户自述“平台只接受人民币”，尚未核实。']}), [PLATFORM_CURRENCY_FLAG])

    def test_negation_is_review_candidate_not_automatic_failure(self):
        self.assertEqual(currency_review_flags({'warnings':['不能推断平台默认币种是人民币。']}), [PLATFORM_CURRENCY_FLAG])

    def test_fact_quotes_are_not_scanned_or_modified(self):
        result={'candidate_facts':[{'value':{'value':'原文引用平台默认币种为人民币'}}],
                'warnings':['不能推断平台常用币种。'],'questions':[]}
        original=copy.deepcopy(result)
        self.assertEqual(currency_review_flags(result), [PLATFORM_CURRENCY_FLAG])
        self.assertEqual(result, original)
        self.assertEqual(currency_review_flags({'candidate_facts':result['candidate_facts']}), [])


if __name__=='__main__':unittest.main()
