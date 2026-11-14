"""V19: reproducible tests for pre-close locks, source matching, costs and evidence gate."""
import copy
from datetime import timedelta
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from tests.test_solo import NOW,sample
from scripts.analyze import create_analysis
from scripts.solo import derive
from scripts.collect import parse_result
from scripts.league_history import build_features
from scripts.feature_model import build as make_form
from scripts.pool_value import build as make_value
from scripts.v19_evaluation import (
    evaluate, score, pick_locked_snapshot, classify, block_ci,
    find_form, choose_report
)
from scripts.v19_decision import build as make_decision, original_ok, safe_system_options


class V19EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.raw=sample()
        self.raw["sha256"]="tested-sha-4444444"
        self.base=create_analysis(self.raw)
        self.solo=derive(self.base,NOW+timedelta(minutes=2))
        self.features=build_features(self.base,[],0,created=NOW+timedelta(minutes=1))
        self.form=make_form(self.base,self.solo,self.features,
                            created=NOW+timedelta(minutes=3))
        self.value=make_value(self.base,self.solo,
                              created=NOW+timedelta(minutes=4))
        doc={"result":{
            "productName":"Stryktipset","drawNumber":9999,
            "events":[{"eventNumber":i,"outcome":"1"} for i in range(1,14)],
            "distribution":[{"name":str(k)+" rätt","amount":100}
                            for k in (10,11,12,13)]}}
        self.result=parse_result(doc,9999,NOW+timedelta(days=3))
        self.now=NOW+timedelta(days=4)

    @staticmethod
    def save(base,relative,obj):
        path=Path(base)/"data"/relative
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(json.dumps(obj),encoding="utf-8")

    def test_replay_original_odds_and_prices(self):
        self.assertTrue(original_ok(self.raw,self.base,NOW+timedelta(minutes=5)))
        tampered=copy.deepcopy(self.base)
        tampered["matches"][0]["p"]=[.8,.1,.1]
        self.assertFalse(original_ok(self.raw,tampered,NOW+timedelta(minutes=5)))

    def test_fixed_locked_source_ignores_after_cutoff_and_later_results(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"data"
            self.save(tmp,"snapshots/9999/old.json",self.raw)
            later=copy.deepcopy(self.raw)
            later["observed_at_utc"]=(NOW+timedelta(hours=11,minutes=50)).isoformat()
            later["sha256"]="later"
            self.save(tmp,"snapshots/9999/later.json",later)
            chosen=pick_locked_snapshot(p,9999,self.now)
            self.assertEqual(chosen["sha256"],"tested-sha-4444444")
            self.save(tmp,"results/9999.json",self.result)
            picked=choose_report(p,9999,self.now)
            self.assertIsNotNone(picked)
            self.assertEqual(picked[1]["source_snapshot_sha256"],self.base["source_snapshot_sha256"])

    def test_form_not_counted_without_replayable_source(self):
        with TemporaryDirectory() as tmp:
            self.save(tmp,"snapshots/9999/old.json",self.raw)
            self.save(tmp,"results/9999.json",self.result)
            self.save(tmp,"form_model/9999.json",self.form)
            r=evaluate(Path(tmp)/"data",self.now)
            self.assertEqual(r["coverage"]["frozen_draws_with_result"],1)
            self.assertEqual(r["factors"][0]["matched_matches"],0)
            self.assertEqual(r["factors"][0]["status"],"otillräckligt underlag")

    def test_form_replay_accepts_source_without_lookahead(self):
        with TemporaryDirectory() as tmp:
            p=Path(tmp)/"data"
            self.save(tmp,"snapshots/9999/old.json",self.raw)
            self.save(tmp,"results/9999.json",self.result)
            self.save(tmp,"form_model/9999.json",self.form)
            self.save(tmp,"form/features/9999.json",self.features)
            report=find_form(p,self.base,self.now)
            self.assertIsNotNone(report)
            r=evaluate(p,self.now)
            self.assertEqual(r["coverage"]["draws_with_form_inputs"],1)
            self.assertEqual(r["factors"][0]["matched_draws"],0) # no form signal, so no paired claim
            self.assertFalse(r["factors"][0]["eligible_for_review"])
            self.assertEqual(r["factors"][2]["matched_matches"],0) # crowd is NOT a 1/X/2 forecast

    def test_probabilities_accurate_and_no_fake_evidence(self):
        self.assertAlmostEqual(score([.6,.25,.15],"1")["brier"],.245)
        self.assertIsNone(block_ci([{"draw":1,"base":{"brier":.5},
                                     "adjusted":{"brier":.45}}]))
        label,eligible,ci=classify([{
            "draw":i//6,"base":{"brier":.64,"logloss":1.0},
            "adjusted":{"brier":.62,"logloss":.99},
        } for i in range(48)],[])
        self.assertEqual(label,"lovande men osäkert")
        self.assertFalse(eligible)

    def test_decision_shadow_never_changes_baseline_cost(self):
        now=NOW+timedelta(minutes=5)
        d=make_decision(self.base,self.raw,self.solo,now,None,self.form,self.value)
        self.assertEqual(len(d["matches"]),13)
        self.assertEqual(set(d["models_available"]),{"form","value"})
        self.assertEqual(d["status"].split(" – ")[0],"förhandsfryst")
        for sys in d["systems"]:
            self.assertIn(sys["budget"],(100,1800))
            self.assertLessEqual(sys["cost"],sys["budget"])
            for candidate in sys["experiments"]:
                self.assertTrue(candidate["same_cost"])
                self.assertFalse(candidate["activated"])
                self.assertEqual(len(candidate["choices"]),13)
                self.assertEqual(sys["cost"],
                                 __import__("math").prod(len(x) for x in candidate["choices"]))

    def test_late_or_wrong_snapshot_rejected(self):
        with self.assertRaises(ValueError):
            make_decision(self.base,self.raw,self.solo,NOW+timedelta(days=2))
        wrong=copy.deepcopy(self.raw)
        wrong["sha256"]="wrong"
        self.assertFalse(original_ok(wrong,self.base,NOW+timedelta(minutes=5)))
        original={100:self.solo["systems"][0],1800:self.base["systems"][0]}
        variants=copy.deepcopy(self.form["budgets"])
        variants[0]["cost"]+=1
        self.assertIsNone(safe_system_options(variants,original,"form"))


if __name__=="__main__":
    unittest.main()
