import copy
import unittest
from datetime import timedelta

from tests.test_solo import sample, NOW
from scripts.analyze import create_analysis, probabilities
from scripts.solo import derive
from scripts.league_history import build_features
from scripts.market_moves import build as make_moves, validate as validate_moves
from scripts.feature_model import (
    build as make_form, validate as validate_form,
    form_adjustment, settle as settle_form,
)
from scripts.collect import parse_result


class NextGenTests(unittest.TestCase):
    def setUp(self):
        self.analysis = create_analysis(sample())
        self.solo = derive(self.analysis, NOW)
        self.form = build_features(self.analysis, [], 0, created=NOW+timedelta(minutes=1))

    def two_observations(self):
        older = copy.deepcopy(self.analysis)
        older["observed_at_utc"] = (NOW-timedelta(hours=2)).isoformat()
        older["source_snapshot_sha256"] = "older-open-api-hash"
        older["matches"][0]["odds"] = [2.65, 3.25, 3.25]
        older["matches"][0]["p"] = [round(x,9) for x in probabilities(older["matches"][0]["odds"])]
        return [older, self.analysis]

    def test_v13_requires_multiple_real_observations(self):
        with self.assertRaises(ValueError):
            make_moves(self.analysis, [self.analysis], NOW+timedelta(minutes=2))

    def test_v13_movement_is_exactly_observed(self):
        xs = self.two_observations()
        report = make_moves(self.analysis, xs, NOW+timedelta(minutes=2))
        self.assertTrue(validate_moves(report, self.analysis, xs))
        self.assertEqual(report["observation_count"],2)
        self.assertEqual(report["matches"][0]["observations"][-1]["p"],
                         self.analysis["matches"][0]["p"])
        self.assertGreater(report["matches"][0]["market_delta_pp"][0],0)
        self.assertEqual(len(report["matches"]),13)
        self.assertNotIn('"outcome":',str(report))

    def test_v13_rejects_wrong_fixture_and_post_close(self):
        xs = self.two_observations()
        xs[0]["matches"][0]["home"]="Other Home"
        with self.assertRaises(ValueError):
            make_moves(self.analysis,xs,NOW+timedelta(minutes=2))
        with self.assertRaises(ValueError):
            make_moves(self.analysis,self.two_observations(),NOW+timedelta(days=1))

    def test_v13_detects_tampering(self):
        xs = self.two_observations()
        report = make_moves(self.analysis,xs,NOW+timedelta(minutes=2))
        report["matches"][0]["market_delta_pp"][0] = 99
        self.assertFalse(validate_moves(report,self.analysis,xs))

    def test_v14_without_forms_is_neutral(self):
        report=make_form(self.analysis,self.solo,self.form,NOW+timedelta(minutes=2))
        self.assertTrue(validate_form(report,self.analysis,self.solo,self.form))
        self.assertEqual(report["matches_with_form"],0)
        for match in report["matches"]:
            self.assertEqual(match["market_p"],match["form_p"])
        for system in report["budgets"]:
            self.assertEqual(system["cost"], 96 if system["budget_limit"]==100 else 1728)
            self.assertEqual(system["cost"],self.product(system["new_choices"]))

    @staticmethod
    def product(choices):
        v=1
        for c in choices:v*=len(c)
        return v

    def test_v14_form_changes_only_when_two_teams_have_data(self):
        db=[]
        for i in range(5):
            db.append({"date":"2026-11-%02d"%(i+1),"home":"home 1",
                       "away":"away 1","home_goals":3,"away_goals":0})
        form=build_features(self.analysis,db,1,created=NOW+timedelta(minutes=1))
        report=make_form(self.analysis,self.solo,form,NOW+timedelta(minutes=2))
        self.assertEqual(report["matches_with_form"],1)
        self.assertGreater(report["matches"][0]["form_p"][0],
                           report["matches"][0]["market_p"][0])
        self.assertEqual(report["matches"][1]["form_p"],
                         report["matches"][1]["market_p"])
        self.assertTrue(validate_form(report,self.analysis,self.solo,form))

    def test_v14_exact_budget_and_input_frozen(self):
        report=make_form(self.analysis,self.solo,self.form,NOW+timedelta(minutes=2))
        for v in report["budgets"]:
            self.assertEqual(self.product(v["original_choices"]),v["cost"])
            self.assertEqual(self.product(v["new_choices"]),v["cost"])
            self.assertGreater(v["new_form_p13"],0)
        tampered=copy.deepcopy(report)
        tampered["budgets"][0]["cost"] += 1
        self.assertFalse(validate_form(tampered,self.analysis,self.solo,self.form))
        with self.assertRaises(ValueError):
            make_form(self.analysis,self.solo,self.form,NOW+timedelta(days=1))
        late=copy.deepcopy(self.form)
        late["created_at_utc"]=(NOW+timedelta(days=1)).isoformat()
        with self.assertRaises(ValueError):
            make_form(self.analysis,self.solo,late,NOW+timedelta(minutes=2))

    def test_v14_settlements_are_hypothetical(self):
        report=make_form(self.analysis,self.solo,self.form,NOW+timedelta(minutes=2))
        doc={"result":{"productName":"Stryktipset","drawNumber":9999,
             "events":[{"eventNumber":i,"outcome":"1"} for i in range(1,14)],
             "distribution":[{"name":str(i)+" rätt","amount":100} for i in (10,11,12,13)]}}
        result=parse_result(doc,9999,NOW+timedelta(days=3))
        settled=settle_form(report,result)
        self.assertTrue(settled["hypothetical"])
        self.assertEqual(settled["n"],13)
        self.assertEqual(len(settled["budgets"]),2)
        for b in settled["budgets"]:
            self.assertEqual(b["market_system"]["cost"],b["form_system"]["cost"])
            self.assertEqual(b["form_system"]["net"],
                             b["form_system"]["paid"]-b["form_system"]["cost"])


if __name__=="__main__":
    unittest.main()
