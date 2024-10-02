# hummingbot/test/hummingbot/connector/exchange/coincheck/test_coincheck_api_order_book_data_source.py

import asyncio
import unittest
from unittest.mock import MagicMock, AsyncMock, patch
from decimal import Decimal
from typing import Any, Dict, List

from hummingbot.connector.exchange.coincheck.coincheck_exchange import CoincheckExchange
from hummingbot.connector.exchange.coincheck.coincheck_api_order_book_data_source import CoincheckAPIOrderBookDataSource
from hummingbot.core.data_type.order_book_message import OrderBookMessage
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource


class TestCoincheckAPIOrderBookDataSource(unittest.TestCase):

    def setUp(self):
        # モックのExchangeクラスを作成
        self.mock_exchange = MagicMock(spec=CoincheckExchange)
        self.mock_exchange.trading_pairs = ["btc-jpy", "eth-jpy"]
        self.mock_exchange.http_request_coincheck = AsyncMock()

        # データソースのインスタンスを作成
        self.data_source = CoincheckAPIOrderBookDataSource(
            trading_pairs=self.mock_exchange.trading_pairs,
            connector=self.mock_exchange
        )

    @patch("hummingbot.connector.exchange.coincheck.coincheck_api_order_book_data_source.OrderBookTrackerDataSource")
    def test_fetch_order_book_snapshot(self, mock_order_book_tracker):
        """
        オーダーブックスナップショットの取得とOrderBookMessageの生成をテストします。
        """
        # スナップショットAPIのモックレスポンス
        mock_snapshot = {
            "pair": "btc-jpy",
            "bids": [{"price": "5000000", "amount": "0.1"}, {"price": "4999000", "amount": "0.2"}],
            "asks": [{"price": "5001000", "amount": "0.1"}, {"price": "5002000", "amount": "0.2"}],
            "updated_at": 1609459200.0  # 2021-01-01 00:00:00 UTC
        }
        self.mock_exchange.http_request_coincheck.return_value = mock_snapshot

        # スナップショットメッセージの処理を確認
        with patch.object(self.data_source._order_book_tracker, 'process_order_book_snapshot') as mock_process:
            asyncio.run(self.data_source._fetch_order_book_snapshot("btc-jpy"))

            # HTTPリクエストが正しく呼び出されたか確認
            self.mock_exchange.http_request_coincheck.assert_awaited_with(
                path=CONSTANTS.ORDER_BOOK_PATH_URL,
                params={"pair": "btc-jpy"},
                http_method="GET"
            )

            # OrderBookMessageが正しく生成されてprocess_order_book_snapshotに渡されたか確認
            expected_message = OrderBookMessage(
                message_type=OrderBookMessage.Type.SNAPSHOT,
                content={
                    "bids": [(Decimal("5000000"), Decimal("0.1")), (Decimal("4999000"), Decimal("0.2"))],
                    "asks": [(Decimal("5001000"), Decimal("0.1")), (Decimal("5002000"), Decimal("0.2"))]
                },
                timestamp=1609459200.0,
                metadata={"trading_pair": "btc-jpy"}
            )
            mock_process.assert_called_once_with("btc-jpy", expected_message)

    @patch("hummingbot.connector.exchange.coincheck.coincheck_api_order_book_data_source.OrderBookTrackerDataSource")
    def test_listen_for_order_book_diffs(self, mock_order_book_tracker):
        """
        オーダーブックの差分データのリッスンとOrderBookMessageの生成をテストします。
        """
        # WebSocketから受信するモックメッセージ
        mock_diff_message = {
            "type": "update",
            "pair": "btc-jpy",
            "bids": [{"price": "5000000", "amount": "0.05"}],
            "asks": [{"price": "5003000", "amount": "0.05"}],
            "timestamp": 1609459201.0
        }

        # WebSocketのモック
        mock_ws = MagicMock()
        mock_ws.__aenter__.return_value = mock_ws
        mock_ws.__aexit__.return_value = False
        mock_ws.iter_messages = AsyncMock(return_value=asyncio.Queue())
        mock_ws.iter_messages.return_value = self._mock_iter_messages([mock_diff_message])

        with patch("aiohttp.ClientSession.ws_connect", return_value=mock_ws):
            with patch.object(self.data_source._order_book_tracker, 'process_order_book_diff') as mock_process:
                asyncio.run(self.data_source.listen_for_order_book_diffs())

                # OrderBookMessageが正しく生成されてprocess_order_book_diffに渡されたか確認
                expected_message = OrderBookMessage(
                    message_type=OrderBookMessage.Type.DIFF,
                    content={
                        "bids": [(Decimal("5000000"), Decimal("0.05"))],
                        "asks": [(Decimal("5003000"), Decimal("0.05"))]
                    },
                    timestamp=1609459201.0,
                    metadata={"trading_pair": "btc-jpy"}
                )
                mock_process.assert_called_once_with("btc-jpy", expected_message)

    async def _mock_iter_messages(self, messages: List[Dict[str, Any]]):
        for msg in messages:
            yield MagicMock(type=aiohttp.WSMsgType.TEXT, json=MagicMock(return_value=msg))


if __name__ == "__main__":
    unittest.main()

