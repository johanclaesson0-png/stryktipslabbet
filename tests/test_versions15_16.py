import copy
import json
import unittest
from datetime import timedelta
from tests.test_solo import sample, NOW
from scripts.analyze import create_analysis
from scripts.solo import derive
from scripts.pool_value import build as build_pool, validate as check_pool, masses, settle as settle_pool
from scripts.other_games import (
    CATEGORIES, SCHEMA, parse_draw, draw_list, analyze, distribution,
    parse_result, settlement, optimize_n
)
from scripts.collect import parse_result as stryk_result


def other_fixture(game, n):
    close=(NOW+timedelta(hours=12)).isoformat()
    events=[]
    for i in range(1,n+1):
        events.append({"eventNumber":i,"cancelled":False,"match":{
            "participants":[{"type":"home","name":"Team home "+str(i)},
                            {"type":"away","name":"Team away "+str(i)}],
            "matchStart":(NOW+timedelta(days=1)).isoformat()},
            "odds":{"one":2.1,"x":3.2,"two":3.5},
            "svenskaFolket":{"one":48,"x":27,"two":25}})
    return {"draw":{"drawNumber":7777,
        "productName":"Topptipset" if game=="topptipset" else "Europatipset",
        "drawState":"Open","regCloseTime":close,"drawEvents":events}}


class V15Tests(unittest.TestCase):
    def setUp(self):
        self.base=create_analysis(sample())
        self.solo=derive(self.base,NOW)
        self.a=build_pool(self.base,self.solo,NOW+timedelta(minutes=1))

    def test_same_budget_and_verified_before_close(self):
        self.assertTrue(check_pool(self.a,self.base,self.solo))
        self.assertEqual(len(self.a["budget_proposals"]),2)
        for b in self.a["budget_proposals"]:
            self.assertEqual(b["cost"],self.cost(b["baseline_choices"]))
            self.assertEqual(b["cost"],self.cost(b["value_choices"]))
            self.assertLessEqual(b["cost"],b["budget_limit"])
            self.assertGreater(b["baseline"]["probability_cover_all_13"],0)
            self.assertGreater(b["value"]["modelled_crowd_cover_mass"],0)

    @staticmethod
    def cost(choices):
        n=1
        for c in choices:n*=len(c)
        return n

    def test_no_future_and_tampering(self):
        with self.assertRaises(ValueError):
            build_pool(self.base,self.solo,NOW+timedelta(days=1))
        changed=copy.deepcopy(self.a)
        changed["budget_proposals"][0]["cost"]=1000
        self.assertFalse(check_pool(changed,self.base,self.solo))
        self.assertNotIn('"outcome":',json.dumps(self.a))

    def test_popularity_does_not_claim_payout(self):
        assert "förväntad" not in self.a.get("estimated_payout","")
        for m in self.a["matches"]:
            self.assertEqual(len(m["p_market"]),3)
        self.assertFalse("expected_win" in str(self.a))

    def test_settlement_official_only(self):
        events=[{"eventNumber":i,"outcome":"1"} for i in range(1,14)]
        result=stryk_result({"result":{"productName":"Stryktipset","drawNumber":9999,
                 "events":events,
                 "distribution":[{"name":str(i)+" rätt","amount":100} for i in (10,11,12,13)]}},
            9999,NOW+timedelta(days=2))
        paid=settle_pool(self.a,result)
        self.assertEqual(len(paid["budget_results"]),2)
        self.assertTrue(paid["hypothetical"])


class V16Tests(unittest.TestCase):
    def test_validate_8_and_13_separately(self):
        for g,n in [("topptipset",8),("europatipset",13)]:
            data=other_fixture(g,n)
            draw=parse_draw(data,g,7777,NOW,"https://example.com",b"fixture")
            self.assertEqual(draw["game"],g)
            self.assertEqual(len(draw["matches"]),n)
            v=analyze(draw,NOW+timedelta(minutes=1))
            self.assertEqual(len(v["systems"]),2 if n==8 else 4)
            for sys in v["systems"]:
                cost=1
                for c in sys["choices"]:cost*=len(c)
                self.assertEqual(cost,sys["cost"])
                self.assertLessEqual(cost,sys["budget_limit"])
                self.assertEqual(len(sys["choices"]),n)
                self.assertGreater(sys["estimated_all_correct"],0)

    def test_reject_mixed_game_and_wrong_match_count(self):
        fixture=other_fixture("topptipset",8)
        with self.assertRaises(ValueError):
            parse_draw(fixture,"europatipset",7777,NOW,"uri",b"x")
        fixture["draw"]["drawEvents"].pop()
        with self.assertRaises(ValueError):
            parse_draw(fixture,"topptipset",7777,NOW,"uri",b"x")

    def test_list_accepts_only_product_and_preclose(self):
        data={"draws":[
            other_fixture("topptipset",8)["draw"],
            other_fixture("europatipset",13)["draw"]
        ]}
        self.assertEqual(len(draw_list(data,"topptipset",NOW)),1)
        self.assertEqual(len(draw_list(data,"europatipset",NOW)),1)
        self.assertEqual(len(draw_list(data,"topptipset",NOW+timedelta(days=1))),0)

    def test_eight_outcome_payout_is_not_13_outcome(self):
        snap=parse_draw(other_fixture("topptipset",8),"topptipset",7777,NOW,"uri",b"payload")
        model=analyze(snap,NOW+timedelta(minutes=1))
        official=parse_result({"result":{"productName":"Topptipset","drawNumber":7777,
                "events":[{"eventNumber":i,"outcome":"1"} for i in range(1,9)],
                "distribution":[{"name":"8 rätt","amount":200}]}},
                "topptipset",7777,NOW+timedelta(days=2),"uri",b"result")
        paid=settlement(model,official)
        self.assertEqual(len(paid["systems"]),2)
        self.assertEqual(len(official["outcome"]),8)
        self.assertEqual(len(distribution(["1X"]*8,"1"*8)),9)
        self.assertIn("8",official["payouts"])
        self.assertNotIn("13",official["payouts"])

    def test_partial_europatips_coupon_never_invents_odds(self):
        fixture=other_fixture("europatipset",13)
        fixture["draw"]["drawEvents"][5]["odds"]=None
        draw=parse_draw(fixture,"europatipset",7777,NOW,"uri",b"raw")
        self.assertEqual(draw["with_valid_odds"],12)
        self.assertIsNone(draw["matches"][5]["p"])
        analysis_doc=analyze(draw,NOW+timedelta(minutes=1))
        self.assertFalse(analysis_doc["complete_odds"])
        self.assertEqual(analysis_doc["systems"],[])

    def test_dont_guess_unknown_results(self):
        with self.assertRaises(ValueError):
            parse_result({"result":{"productName":"Europatipset","drawNumber":7777,
              "events":[{"eventNumber":i,"outcome":"X"} for i in range(1,14)],
              "distribution":[]}},"europatipset",7777,NOW+timedelta(days=2),"uri",b"x")

if __name__=="__main__":
    unittest.main()
