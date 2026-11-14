"""V20: Monte Carlo payout scenario safety, equal-cost controls and assumptions."""
import copy
from datetime import timedelta
import math
import unittest

from tests.test_solo import NOW, sample
from scripts.analyze import create_analysis
from scripts.solo import derive
from scripts.v20_payout_simulator import (
    RETURN_FRACTION,POOL_SHARES,SAMPLES,MIN_PAYOUT,
    crowds_class_likelihood,valid_probability_rows,generate_candidates,
    sample_outcomes,winning_rows,potential_payout,analyze_strategies,
    build,SCHEMA,
)


class PayoutSimulatorV20Tests(unittest.TestCase):
    def setUp(self):
        self.snapshot=sample()
        self.snapshot["sha256"]="v20-unmodified-snapshot"
        self.original=create_analysis(self.snapshot)
        self.personal=derive(self.original,NOW+timedelta(minutes=1))
        self.budgets={
            100:(self.personal["systems"][0]["cost"],self.personal["systems"][0]["choices"]),
            1800:(self.original["systems"][0]["cost"],self.original["systems"][0]["choices"])
        }

    def test_payout_shares_and_refund_are_not_100_percent(self):
        self.assertAlmostEqual(sum(POOL_SHARES.values()),.92)
        self.assertAlmostEqual(RETURN_FRACTION, .65)
        self.assertEqual(tuple(sorted(POOL_SHARES)),(10,11,12,13))

    def test_poisson_binomial_dist_is_correct(self):
        # For all identical 100% home selections, row always has 13 hits
        crowd=[[1.,0.,0.] for _ in range(13)]
        counts=crowds_class_likelihood(crowd,tuple([0]*13))
        self.assertAlmostEqual(counts[13],1.)
        self.assertAlmostEqual(counts[12],0.)
        self.assertAlmostEqual(counts[11],0.)
        self.assertAlmostEqual(counts[10],0.)
        crowd=[[.5,.5,0.] for _ in range(13)]
        probs=crowds_class_likelihood(crowd,tuple([0]*13))
        self.assertAlmostEqual(probs[13],.5**13)
        self.assertAlmostEqual(probs[12],13*.5**13)

    def test_systems_always_match_original_stakes(self):
        for budget,(cost,choices) in self.budgets.items():
            variants=generate_candidates(self.original["matches"],choices,cost)
            self.assertEqual(variants["odds"],choices)
            self.assertEqual(len(variants),5)
            for v in variants.values():
                self.assertEqual(math.prod(len(x) for x in v),cost)
                self.assertLessEqual(cost,budget)

    def test_zero_competing_winners_excludes_jackpot(self):
        rows=[0]*14
        rows[13]=1
        expected=1_000_000*.65*.4
        gain=potential_payout(rows,{k:0 for k in (10,11,12,13)},1_000_000,1.0)
        self.assertAlmostEqual(gain,expected)
        self.assertLess(gain,10_000_000) # not guaranteed and labelled
        # Crowded category below threshold should not pay in base scenario
        low=potential_payout(rows,{k:1e9 for k in (10,11,12,13)},1_000_000,1.0)
        self.assertEqual(low,0.)

    def test_reproducible_draws_with_fair_common_random_numbers(self):
        p,_=valid_probability_rows(self.original["matches"])
        a=sample_outcomes(p,350,42)
        b=sample_outcomes(p,350,42)
        self.assertEqual(a,b)
        self.assertNotEqual(a,sample_outcomes(p,350,43))
        for outcome in a[:5]:
            dist=winning_rows(self.budgets[100][1],outcome)
            self.assertEqual(sum(dist),self.budgets[100][0])

    def test_competing_multiplier_is_explicit_sensitivity(self):
        rows=[0]*14;rows[13]=1
        other={k:4 for k in (10,11,12,13)}
        high=potential_payout(rows,other,5_000_000,0.5)
        low=potential_payout(rows,other,5_000_000,2)
        self.assertGreater(high,low)

    def test_build_scenarios_and_no_actual_turnover_claim(self):
        report=build(self.snapshot,self.original,self.personal,
                     NOW+timedelta(minutes=3),simulations=350)
        self.assertEqual(report["schema"],SCHEMA)
        self.assertEqual(report["simulation_draws"],350)
        self.assertEqual(len(report["scenarios"]),9)
        self.assertEqual(report["draw_number"],9999)
        self.assertIn("ILLUSTRATIVE",report["assumptions"]["turnover"])
        self.assertNotIn("actual_turnover_kr",report)
        for scenario in report["scenarios"]:
            self.assertEqual(len(scenario["budgets"]),2)
            for x in scenario["budgets"]:
                self.assertEqual(len(x["strategies"]),5)
                for system in x["strategies"]:
                    self.assertEqual(system["cost"],x["exact_cost"])
                    self.assertEqual(math.prod(len(s) for s in system["choices"]),x["exact_cost"])
                    self.assertGreaterEqual(system["prob_at_least_one_13"],0)
                    self.assertLessEqual(system["prob_at_least_one_13"],1)

    def test_reject_postclose_and_changed_origin(self):
        with self.assertRaises(ValueError):
            build(self.snapshot,self.original,self.personal,NOW+timedelta(days=2),350)
        tampered=copy.deepcopy(self.snapshot)
        tampered["matches"][0]["odds"]=[100,2,2]
        with self.assertRaises(ValueError):
            build(tampered,self.original,self.personal,NOW+timedelta(minutes=3),350)


if __name__=="__main__":
    unittest.main()
