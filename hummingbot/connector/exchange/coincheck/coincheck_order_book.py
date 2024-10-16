from typing import Dict, Optional
from hummingbot.core.data_type.common import TradeType
from hummingbot.core.data_type.order_book import OrderBook
from hummingbot.core.data_type.order_book_message import OrderBookMessage, OrderBookMessageType
from hummingbot.logger import HummingbotLogger

class CoincheckOrderBook(OrderBook):
    _logger: Optional[HummingbotLogger] = None

    @classmethod
    def logger(cls) -> HummingbotLogger:
        if cls._logger is None:
            cls._logger = HummingbotLogger.get_logger(__name__)
        return cls._logger

    @classmethod
    def snapshot_message_from_exchange(cls,msg: Dict[str, any], timestamp: float, metadata: Optional[Dict] = None) -> OrderBookMessage:
        
        if metadata:
            msg.update(metadata)
        
        return OrderBookMessage(OrderBookMessageType.SNAPSHOT, {
            "trading_pair": msg.get("trading_pair", ""),  
            "update_id": msg.get("lastUpdateId"),
            "bids": msg.get("bids", []),
            "asks": msg.get("asks", [])
        }, timestamp=timestamp)

    @classmethod
    def diff_message_from_exchange(cls,
                                   msg: Dict[str, any],
                                   timestamp: Optional[float] = None,
                                   metadata: Optional[Dict] = None) -> OrderBookMessage:
        # Update metadata if available
        if metadata:
            msg.update(metadata)
        # Create the diff message for order book updates
        return OrderBookMessage(OrderBookMessageType.DIFF, {
            "trading_pair": msg.get("trading_pair", ""),  
            "first_update_id": msg.get("U"),  
            "update_id": msg.get("u"),        
            "bids": msg.get("b", []),         
            "asks": msg.get("a", [])          
        }, timestamp=timestamp)

    @classmethod
    def trade_message_from_exchange(cls, msg: Dict[str, any], metadata: Optional[Dict] = None) -> OrderBookMessage:
        # Log error if something goes wrong (updated to use cls.logger())
        cls.logger().error("Trade message processing error!")
        
        # Update metadata if available
        if metadata:
            msg.update(metadata)
        
        # Process trade message
        ts = msg.get("E")  
        return OrderBookMessage(OrderBookMessageType.TRADE, {
            "trading_pair": msg.get("trading_pair", ""),
            "trade_type": float(TradeType.SELL.value) if msg.get("m") else float(TradeType.BUY.value),
            "trade_id": msg.get("t"),
            "update_id": ts,
            "price": msg.get("p"),
            "amount": msg.get("q")
        }, timestamp=ts * 1e-3)

    # Example function to display the order book in the terminal
    def display_order_book(cls):
        bids = cls.bids
        asks = cls.asks
        
        print(f"Order Book for {cls.trading_pair}:")
        print("\nBids:")
        for bid in bids:
            print(f"Price: {bid[0]}, Amount: {bid[1]}")
        
        print("\nAsks:")
        for ask in asks:
            print(f"Price: {ask[0]}, Amount: {ask[1]}")