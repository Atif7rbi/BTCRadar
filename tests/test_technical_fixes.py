from __future__ import annotations

import io
import logging
import os
import unittest
from types import SimpleNamespace

from src.app import _app_port
from src.logger import get_logger
from src.services.trade_service import TradeService


class PortConfigTests(unittest.TestCase):
    def tearDown(self):
        os.environ.pop('BTCRADAR_PORT', None)

    def test_app_port_respects_env_override(self):
        os.environ['BTCRADAR_PORT'] = '6123'

        self.assertEqual(_app_port({'app': {'port': 5005}}), 6123)

    def test_app_port_falls_back_to_config(self):
        os.environ.pop('BTCRADAR_PORT', None)

        self.assertEqual(_app_port({'app': {'port': 5006}}), 5006)


class LoggerBehaviorTests(unittest.TestCase):
    def setUp(self):
        self._reset_btcradar_loggers()

    def tearDown(self):
        self._reset_btcradar_loggers()

    def test_child_loggers_do_not_create_duplicate_handlers(self):
        base = get_logger('BTCRadar')
        child = get_logger('BTCRadar.Coinalyze')

        self.assertGreaterEqual(len(base.handlers), 1)
        self.assertEqual(len(child.handlers), 0)
        self.assertTrue(child.propagate)
        self.assertFalse(base.propagate)

    def test_child_log_propagation_writes_one_line(self):
        base = get_logger('BTCRadar')
        child = get_logger('BTCRadar.Coinalyze')

        for handler in list(base.handlers):
            base.removeHandler(handler)
            handler.close()

        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setFormatter(logging.Formatter('%(name)s:%(message)s'))
        base.addHandler(handler)

        child.info('single propagation check')
        handler.flush()

        lines = [line for line in stream.getvalue().splitlines() if line]
        self.assertEqual(lines, ['BTCRadar.Coinalyze:single propagation check'])

    def _reset_btcradar_loggers(self):
        for name in ('BTCRadar', 'BTCRadar.Coinalyze'):
            logger = logging.getLogger(name)
            for handler in list(logger.handlers):
                logger.removeHandler(handler)
                handler.close()
            logger.propagate = True


class TradeCloseMetadataTests(unittest.TestCase):
    def test_close_metadata_includes_cvd_delta_and_trend(self):
        market = SimpleNamespace(
            cfg={'symbols': {'driver': 'BTCUSDT'}},
            snapshots={
                'BTCUSDT': SimpleNamespace(
                    cvd=10.12345,
                    cvd_pressure='BUY',
                    cvd_delta_15m=2.5,
                    cvd_trend='RISING',
                ),
                'ETHUSDT': SimpleNamespace(
                    cvd=-3,
                    cvd_pressure='SELL',
                    cvd_delta_15m=-1.25,
                    cvd_trend='FALLING',
                ),
            },
        )

        meta = TradeService(None, market)._build_close_metadata('ETHUSDT')

        self.assertEqual(meta['btc_cvd_delta_15m_at_close'], 2.5)
        self.assertEqual(meta['btc_cvd_trend_at_close'], 'RISING')
        self.assertEqual(meta['follower_cvd_delta_15m_at_close'], -1.25)
        self.assertEqual(meta['follower_cvd_trend_at_close'], 'FALLING')

    def test_close_metadata_missing_values_remain_none(self):
        market = SimpleNamespace(
            cfg={'symbols': {'driver': 'BTCUSDT'}},
            snapshots={
                'BTCUSDT': SimpleNamespace(cvd=None, cvd_pressure=None),
                'ETHUSDT': SimpleNamespace(cvd=None, cvd_pressure=None),
            },
        )

        meta = TradeService(None, market)._build_close_metadata('ETHUSDT')

        self.assertIsNone(meta['btc_cvd_delta_15m_at_close'])
        self.assertIsNone(meta['btc_cvd_trend_at_close'])
        self.assertIsNone(meta['follower_cvd_delta_15m_at_close'])
        self.assertIsNone(meta['follower_cvd_trend_at_close'])


if __name__ == '__main__':
    unittest.main()
