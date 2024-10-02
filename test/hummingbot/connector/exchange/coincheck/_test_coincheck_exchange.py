# hummingbot/test/hummingbot/connector/exchange/coincheck/test_coincheck_exchange.py

import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from hummingbot.connector.exchange.coincheck.coincheck_exchange import CoincheckExchange
from hummingbot.connector.exchange.coincheck.coincheck_api_order_book_data_source import CoincheckAPIOrderBookDataSource
from hummingbot.core.api_throttler.async_throttler import AsyncThrottler
from hummingbot.connector.exchange.coincheck import coincheck_constants as CONSTANTS
import os
from hummingbot.client.config.config_helpers import ClientConfigAdapter
from hummingbot.core.api_throttler.data_types import RateLimit
from decimal import Decimal
api_key = os.environ.get('CC_API_KEY')
secret_key = os.environ.get('CC_SECRET_KEY')
class TestCoincheckExchange(unittest.TestCase):

    def setUp(self):
        # モックのClientConfigAdapterを作成
        self.mock_client_config_map = MagicMock(spec=ClientConfigAdapter)
        # self.mock_client_config_map = MagicMock()
        # anonymized_metrics_mode を設定
        self.mock_anonymized_metrics_mode = MagicMock()
        self.mock_client_config_map.anonymized_metrics_mode = self.mock_anonymized_metrics_mode
        self.mock_anonymized_metrics_mode.get_collector.return_value = MagicMock()
        # instance_id を設定
        self.mock_client_config_map.instance_id = "test_instance_id"
        
        # rate_limits_rules を設定
        self.mock_client_config_map.rate_limits_rules = CONSTANTS.RATE_LIMITS

                # rate_limits_share_pct を設定
        self.mock_client_config_map.rate_limits_share_pct = 1.0  # 適切な値を設定
        # self.mock_client_config_map.rate_limits_share_pct = Decimal("1.0")  # Decimal型で設定
   
        # APIキーとシークレットキーの設定
        self.api_key =  api_key
        self.secret_key = secret_key

        # 取引ペアのリスト
        self.trading_pairs = ["btc-jpy", "eth-jpy"]

        # モックのAsyncThrottler
        self.mock_throttler = MagicMock(spec=AsyncThrottler)

        # CoincheckExchangeのインスタンス作成
        self.coincheck_exchange = CoincheckExchange(
            client_config_map=self.mock_client_config_map,
            coincheck_api_key=self.api_key,
            coincheck_api_secret=self.secret_key,
            trading_pairs=self.trading_pairs,
            trading_required=True
        )

    #@patch("hummingbot.connector.exchange_py_base.AsyncThrottler")
    #@patch("hummingbot.core.api_throttler.async_throttler.AsyncThrottler", autospec=True)
    #@patch("hummingbot.core.api_throttler.async_throttler_base.AsyncThrottler", autospec=True)
    # @patch("hummingbot.core.api_throttler.async_throttler.AsyncThrottler", autospec=True)
    @patch("hummingbot.core.api_throttler.async_throttler.AsyncThrottler", autospec=True)
    def test_async_throttler_initialization(self, mock_throttler):
        # RATE_LIMITS が正しく渡されているか確認
        self.assertEqual(self.coincheck_exchange.rate_limits_rules, CONSTANTS.RATE_LIMITS)
        
        # RATE_LIMITS の各 RateLimit インスタンスに具体的な limit を設定
        for rate_limit in CONSTANTS.RATE_LIMITS:
            rate_limit.limit =  Decimal("100")  # 具体的な数値に設定
        
        mock_throttler.assert_called_with(rate_limits=CONSTANTS.RATE_LIMITS, limits_share_percentage=Decimal("1.0"))

    def test_trading_pairs_set_correctly(self):
        self.assertEqual(self.coincheck_exchange.trading_pairs, self.trading_pairs)


if __name__ == '__main__':
    unittest.main()
