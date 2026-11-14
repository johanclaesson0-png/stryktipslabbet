"""V21 official turnover + winner counts and strict preclose audit, no network."""
from datetime import datetime,timedelta,timezone
import copy
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from tests.test_solo import NOW,sample
from scripts.collect import parse_draw
from scripts.v21_pool_history import (
    currency_int,parse_official,compare,backfill,SCHEMA as POOLS,
)
from scripts.v21_calibration import historical_summary,prospective_comparison,build
from scripts.v20_payout_simulator import SCHEMA as V20


def public_result(draw=4978,turnover="33004181,00"):
    return {"result":{
        "drawNumber":draw,"productName":"Stryktipset","productId":1,
        "currentNetSale":turnover,"cancelled":False,
        "events":[{"eventNumber":i,"outcome":"1"} for i in range(1,14)],
        "distribution":[
            {"name":"13 rätt","winners":9,"amount":"1444444,00"},
            {"name":"12 rätt","winners":438,"amount":"7346,00"},
            {"name":"11 rätt","winners":6341,"amount":"405,00"},
            {"name":"10 rätt","winners":54475,"amount":"98,00"}]}}


class RealPayoutV21Tests(unittest.TestCase):
    def test_official_numeric_and_winner_class_fields(self):
        self.assertEqual(currency_int("33 004 181,00"),33004181)
        self.assertRaises(ValueError,currency_int,"33 004 181,12")
        self.assertRaises(ValueError,currency_int,None)
        self.assertRaises(ValueError,currency_int,"123e99")
        x=parse_official(public_result(),4978,NOW)
        self.assertEqual(x["turnover_kr"],33004181)
        self.assertEqual(x["classes"]["13"]["winners"],9)
        self.assertEqual(x["classes"]["10"]["winners"],54475)
        self.assertEqual(x["classes"]["13"]["payout_per_row_kr"],1444444)
        self.assertEqual(x["time_type"],"after_final_result_not_preclose")

    def test_reject_mismatched_draw_or_winners_or_distribution(self):
        self.assertRaises(ValueError,parse_official,public_result(),4977,NOW)
        doc=public_result();doc["result"]["distribution"][0]["winners"]=-1
        self.assertRaises(ValueError,parse_official,doc,4978,NOW)
        doc=public_result();doc["result"]["distribution"][0]["amount"]="1444444,35"
        self.assertRaises(ValueError,parse_official,doc,4978,NOW)
        doc=public_result();doc["result"]["currentNetSale"]="99,00"
        self.assertRaises(ValueError,parse_official,doc,4978,NOW)
        x=parse_official(public_result(),4978,NOW)
        self.assertRaises(ValueError,compare,x,{
            "outcome":"X"*13,
            "payouts":{str(k):x["classes"][str(k)]["payout_per_row_kr"] for k in (10,11,12,13)}
        })

    def test_backfill_idempotence_and_official_crosscheck(self):
        expected={4978:{"outcome":"1"*13,
            "payouts":{"10":98,"11":405,"12":7346,"13":1444444}}}
        with TemporaryDirectory() as tmp:
            path=Path(tmp);(path/"data"/"history").mkdir(parents=True)
            calls=[]
            def transport(route):
                calls.append(route)
                return public_result(),b"x"
            with patch("scripts.v21_pool_history.source_expectations",return_value=expected):
                one=backfill(path,limit=1,transport=transport,nap=0,now=NOW)
                two=backfill(path,limit=1,transport=transport,nap=0,now=NOW)
            self.assertEqual(one["verified_count"],1)
            self.assertEqual(two["verified_count"],1)
            self.assertEqual(len(calls),1)
            data=json.loads((path/"data"/"history"/"official_pools.json").read_text())
            self.assertEqual(data["schema"],POOLS)
            self.assertEqual(data["draws"]["4978"]["turnover_kr"],33004181)

    def test_actual_history_is_not_fabricated_preclose_crowd(self):
        draw=parse_official(public_result(),4978,NOW)
        stats=historical_summary({"4978":draw})
        self.assertEqual(stats["draws_with_official_turnover_winners"],1)
        self.assertEqual(stats["by_class"]["13"]["winner_rows_median"],9)
        self.assertGreater(stats["by_class"]["13"]["observed_vs_simple_pool_ratio_median"],0)
        with TemporaryDirectory() as tmp:
            data=Path(tmp)/"data";(data/"history").mkdir(parents=True)
            (data/"history"/"official_pools.json").write_text(json.dumps({
                "schema":POOLS,"draws":{"4978":draw}}))
            report=build(data,NOW+timedelta(days=2))
            self.assertEqual(report["historical_actuals"]["draws_with_official_turnover_winners"],1)
            self.assertEqual(report["prospective_model_check"][
                "prospective_draws_with_preclose_streck_and_official_winners"],0)
            self.assertEqual(report["prospective_model_check"][
                "class_error"]["13"]["actual_to_independent_crowd_ratio_median"],None)

    def test_preclose_crowd_only_when_snapshot_and_result_match(self):
        raw=sample()
        raw["sha256"]="preclose-verified-hash"
        draw=raw["draw_number"]
        official=public_result(draw)
        source=parse_official(official,draw,NOW+timedelta(days=2))
        source["outcome"]="1"*13
        with TemporaryDirectory() as tmp:
            data=Path(tmp)/"data"
            d=data/"snapshots"/str(draw);d.mkdir(parents=True)
            (d/"preclose.json").write_text(json.dumps(raw))
            reports=prospective_comparison(data,{str(draw):source})
            self.assertEqual(reports["prospective_draws_with_preclose_streck_and_official_winners"],1)
            self.assertFalse(reports["class_error"]["13"]["reliable_for_multiplier_calibration"])
            # Tampering with timestamp makes it ineligible
            raw["observed_at_utc"]=(NOW+timedelta(hours=12)).isoformat()
            (d/"preclose.json").write_text(json.dumps(raw))
            reports=prospective_comparison(data,{str(draw):source})
            self.assertEqual(reports["prospective_draws_with_preclose_streck_and_official_winners"],0)

    def test_not_frozen_v20_scenarios_never_count_as_settled_systems(self):
        with TemporaryDirectory() as tmp:
            data=Path(tmp)/"data";data.mkdir()
            source=parse_official(public_result(),4978,NOW+timedelta(days=2))
            (data/"v20").mkdir()
            (data/"v20"/"simulator.json").write_text(json.dumps({
                "schema":V20,"draw_number":4978,
                "generated_at_utc":(NOW+timedelta(days=2)).isoformat(),
                "scenarios":[{"budgets":[]}]}))
            x=prospective_comparison(data,{"4978":source})
            self.assertEqual(x["correctly_frozen_v20_strategy_draws"],0)


if __name__=="__main__":
    unittest.main()
