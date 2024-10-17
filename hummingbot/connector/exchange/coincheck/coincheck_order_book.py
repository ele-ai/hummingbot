from typing import Dict, Optional
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.logger import HummingbotLogger


class CoincheckOrderBook(OrderBook):
    _logger: Optional[HummingbotLogger] = None

    # Define supported trading pairs with their appropriate formats
    COINCHECK_TRADING_PAIRS = {
        "BRIL/JPY": "bril-jpy",
        # Add more trading pairs as needed
    }

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = HummingbotLogger.get_logger(__name__)
        return cls._logger

    @classmethod
    def is_valid_market(cls, trading_pair: str) -> bool:
        """Checks if the trading pair is valid and supported."""
        return trading_pair.upper() in cls.COINCHECK_TRADING_PAIRS

    @classmethod
    def format_trading_pair(cls, trading_pair: str) -> str:
        """Format trading pairs to the format recognized by Coincheck."""
        return cls.COINCHECK_TRADING_PAIRS.get(trading_pair.upper(), None)

    @classmethod
    def snapshot_message_from_exchange(cls, msg: Dict[str, any], timestamp: float, metadata: Optional[Dict] = None) -> OrderBookMessage:
        """Creates a snapshot message for the order book."""
        trading_pair = cls.format_trading_pair(msg.get("trading_pair", ""))
        if trading_pair is None:
            cls.logger().error(f"Invalid trading pair: {msg.get('trading_pair')}")
            raise ValueError("Invalid trading pair")

        if metadata:
            msg.update(metadata)
        
        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": trading_pair,
            "update_id": msg.get("lastUpdateId"),
            "bids": msg.get("bids", []),
            "asks": msg.get("asks", [])
        }, timestamp=timestamp)

    @classmethod
    def diff_message_from_exchange(cls, msg: Dict[str, any], timestamp: Optional[float] = None, metadata: Optional[Dict] = None) -> OrderBookMessage:
        """Creates a diff message for order book updates."""
        trading_pair = cls.format_trading_pair(msg.get("trading_pair", ""))
        if trading_pair is None:
            cls.logger().error(f"Invalid trading pair: {msg.get('trading_pair')}")
            raise ValueError("Invalid trading pair")

        if metadata:
            msg.update(metadata)

        return OrderBookMessage(OrderBookMessageType.DIFF, {
            "trading_pair": trading_pair,
            "first_update_id": msg.get("U"),
            "update_id": msg.get("u"),
            "bids": msg.get("b", []),
            "asks": msg.get("a", [])
        }, timestamp=timestamp)

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None) -> OrderBookMessage:
        """Processes a trade message."""
        trading_pair = cls.format_trading_pair(msg.get("trading_pair", ""))
        if trading_pair is None:
            cls.logger().error(f"Invalid trading pair: {msg.get('trading_pair')}")
            raise ValueError("Invalid trading pair")

        # Update metadata if available
        if metadata:
            msg.update(metadata)

        ts = msg.get("E")  # Event time
        return OrderBookMessage(OrderBookMessageType.TRADE, {
            "trading_pair": trading_pair,
            "trade_type": float(TradeType.SELL.value) if msg.get("m") else float(TradeType.BUY.value),
            "trade_id": msg.get("t"),
            "update_id": ts,
            "price": msg.get("p"),
            "amount": msg.get("q")
        }, timestamp=ts * 1e-3)

    @classmethod
    def display_order_book(cls):
        """Displays the current order book in the terminal."""
        bids = cls.bids
        asks = cls.asks

        print(f"Order Book for {cls.trading_pair}:")
        print("\nBids:")
        for bid in bids:
            print(f"Price: {bid[0]}, Amount: {bid[1]}")

        print("\nAsks:")
        for ask in asks:
            print(f"Price: {ask[0]}, Amount: {ask[1]}")
