from __future__ import annotations

import unittest

from src.services.validation_report import ValidationReport


class ValidationReportTests(unittest.TestCase):
    def test_report_contains_required_sections_and_sample_sizes(self):
        report = ValidationReport([
            {
                'symbol': 'ETHUSDT',
                'direction': 'LONG',
                'pnl_usd': 5,
                'pnl_pct': 5,
                'duration_sec': 1800,
                'btc_spread_at_entry': 32,
                'btc_state_at_entry': 'BTC_SHORT_CROWDED',
                'btc_recommendation_at_entry': 'LONG FOLLOWERS',
                'follow_score_at_entry': 72,
                'btc_health_status_at_entry': 'SAFE',
                'follower_health_status_at_entry': 'SAFE',
                'btc_preferred_direction_at_entry': 'LONG',
                'follower_preferred_direction_at_entry': 'LONG',
                'btc_funding_at_entry': 0.00001,
                'follower_funding_at_entry': -0.00001,
                'btc_cvd_trend_at_entry': 'RISING',
                'follower_cvd_trend_at_entry': 'RISING',
                'btc_cvd_delta_entry_to_close': 2,
                'follower_cvd_delta_entry_to_close': 3,
                'exit_reason': 'MANUAL_CLOSE',
            },
            {
                'symbol': 'SOLUSDT',
                'direction': 'SHORT',
                'pnl_usd': -2,
                'pnl_pct': -2,
                'duration_sec': 300,
                'btc_spread_at_entry': None,
                'btc_state_at_entry': None,
                'btc_recommendation_at_entry': None,
                'follow_score_at_entry': None,
                'btc_health_status_at_entry': None,
                'follower_health_status_at_entry': None,
                'btc_preferred_direction_at_entry': None,
                'follower_preferred_direction_at_entry': None,
                'btc_funding_at_entry': None,
                'follower_funding_at_entry': None,
                'btc_cvd_trend_at_entry': None,
                'follower_cvd_trend_at_entry': None,
                'btc_cvd_delta_entry_to_close': None,
                'follower_cvd_delta_entry_to_close': None,
                'exit_reason': None,
            },
        ]).to_dict()

        for key in (
            'summary',
            'sample_quality',
            'entry_validation',
            'alignment_validation',
            'funding_validation',
            'cvd_validation',
            'exit_validation',
            'symbol_validation',
            'risk_flags',
            'conclusions',
            'next_data_needed',
        ):
            self.assertIn(key, report)

        self.assertEqual(report['summary']['sample_size'], 2)
        spread_rows = report['entry_validation']['btc_spread_buckets']
        self.assertTrue(all('sample_size' in row for row in spread_rows))
        self.assertEqual(
            next(row for row in spread_rows if row['label'] == 'Spread 30+')['sample_size'],
            1,
        )
        self.assertEqual(
            next(row for row in spread_rows if row['label'] == 'Legacy / Missing')['sample_size'],
            1,
        )

    def test_risk_flags_include_required_codes(self):
        report = ValidationReport([]).to_dict()

        codes = {flag['code'] for flag in report['risk_flags']}

        self.assertEqual(
            {
                'LOW_SAMPLE',
                'MISSING_METADATA',
                'LEGACY_TRADES',
                'SELECTION_BIAS_RISK',
                'NO_COST_MODEL',
                'NO_OPPORTUNITY_SET',
            },
            codes,
        )


if __name__ == '__main__':
    unittest.main()
