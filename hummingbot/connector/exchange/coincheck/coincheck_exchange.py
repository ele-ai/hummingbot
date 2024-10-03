import asyncio
import json
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple
from urllib.parse import urlencode
import ast

import aiohttp
from bidict import bidict

from hummingbot.connector.constants import s_decimal_NaN
from hummingbot.connector.exchange.coincheck import (
    coincheck_constants as CONSTANTS,
    coincheck_utils,
    coincheck_web_utils as web_utils,
)
from hummingbot.connector.exchange.coincheck.coincheck_api_order_book_data_source import CoincheckAPIOrderBookDataSource
from hummingbot.connector.exchange.coincheck.coincheck_api_user_stream_data_source import (
    CoincheckAPIUserStreamDataSource,
)
from hummingbot.connector.exchange.coincheck.coincheck_auth import CoincheckAuth
from hummingbot.connector.exchange_py_base import ExchangePyBase
from hummingbot.connector.parrot import logger
from hummingbot.connector.trading_rule import TradingRule
from hummingbot.connector.utils import TradeFillOrderDetails, combine_to_hb_trading_pair
from hummingbot.core.data_type.common import OrderType, TradeType
from hummingbot.core.data_type.in_flight_order import InFlightOrder, OrderUpdate, TradeUpdate
from hummingbot.core.data_type.order_book_tracker_data_source import OrderBookTrackerDataSource
from hummingbot.core.data_type.trade_fee import DeductedFromReturnsTradeFee, TokenAmount, TradeFeeBase
from hummingbot.core.data_type.user_stream_tracker_data_source import UserStreamTrackerDataSource
from hummingbot.core.event.events import MarketEvent, OrderFilledEvent
from hummingbot.core.utils.async_utils import safe_gather
from hummingbot.core.web_assistant.connections.data_types import RESTMethod
from hummingbot.core.web_assistant.web_assistants_factory import WebAssistantsFactory

if TYPE_CHECKING:
    from hummingbot.client.config.config_helpers import ClientConfigAdapter


class CoincheckExchange(ExchangePyBase):
    UPDATE_ORDER_STATUS_MIN_INTERVAL = 10.0
    web_utils = web_utils

    def __init__(self,
                 client_config_map: "ClientConfigAdapter",
                 coincheck_api_key: str,
                 coincheck_api_secret: str,
                 trading_pairs: Optional[List[str]] = None,
                 trading_required: bool = True,
                 ):
        self.api_key = coincheck_api_key
        self.secret_key = coincheck_api_secret
        self._trading_required = trading_required
        self._trading_pairs = trading_pairs
        self._last_trades_poll_coincheck_timestamp = 1.0
        super().__init__(client_config_map)

    @staticmethod
    def coincheck_order_type(order_type: OrderType) -> str:
        return order_type.name.upper()

    @staticmethod
    def to_hb_order_type(coincheck_type: str) -> OrderType:
        return OrderType[coincheck_type]

    @property
    def authenticator(self):
        return CoincheckAuth(
            access_key=self.api_key,
            secret_key=self.secret_key)

    @property
    def name(self) -> str:
            return "coincheck"

    @property
    def domain(self) -> str:
        return "com"
    
    @property
    def rate_limits_rules(self):
        return CONSTANTS.RATE_LIMITS

    @property
    def client_order_id_max_length(self):
        return CONSTANTS.MAX_ORDER_ID_LEN

    @property
    def client_order_id_prefix(self):
        return CONSTANTS.HBOT_ORDER_ID_PREFIX

    @property
    def trading_rules_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def trading_pairs_request_path(self):
        return CONSTANTS.EXCHANGE_INFO_PATH_URL

    @property
    def check_network_request_path(self):
        return CONSTANTS.PING_PATH_URL

    @property
    def trading_pairs(self):
        return self._trading_pairs

    @property
    def is_cancel_request_in_exchange_synchronous(self) -> bool:
        return True

    @property
    def is_trading_required(self) -> bool:
        return self._trading_required
	
    async def http_request_coincheck(self,path:str,params=None,http_method="GET"):
        path_url=CONSTANTS.REST_URL+path
        header=self.authenticator.get_headers(path)
        try:
            async with aiohttp.ClientSession() as session:
                if http_method=="GET":
                    async with session.get(path_url, params=params, headers=header) as response:
                        resp_json = await response.json()
                elif http_method=="POST":        
                    async with session.post(path_url, params=params, headers=header) as response:
                        resp_json = await response.json()
                elif http_method=="DELETE":
                    async with session.delete(path_url, params=params, headers=header) as response:
                        resp_json = await response.json()
        except Exception as error:
            self.logger().error(f"Error Request:{error}")
            return
        return resp_json

    def supported_order_types(self):
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]
        return [OrderType.LIMIT, OrderType.LIMIT_MAKER, OrderType.MARKET]

    def _is_request_exception_related_to_time_synchronizer(self, request_exception: Exception):
        error_description = str(request_exception)
        is_time_synchronizer_related = ("-1021" in error_description
                                        and "Timestamp for this request" in error_description)
        return is_time_synchronizer_related

    def _is_order_not_found_during_status_update_error(self, status_update_exception: Exception) -> bool:
        return str(CONSTANTS.ORDER_NOT_EXIST_ERROR_CODE) in str(
            status_update_exception
        ) and CONSTANTS.ORDER_NOT_EXIST_MESSAGE in str(status_update_exception)

    def _is_order_not_found_during_cancelation_error(self, cancelation_exception: Exception) -> bool:
        return str(CONSTANTS.UNKNOWN_ORDER_ERROR_CODE) in str(
            cancelation_exception
        ) and CONSTANTS.UNKNOWN_ORDER_MESSAGE in str(cancelation_exception)

    def _create_web_assistants_factory(self) -> WebAssistantsFactory:
        return web_utils.build_api_factory(
            throttler=self._throttler,
            time_synchronizer=self._time_synchronizer,
            domain=self.domain,
            auth=self._auth)

    def _create_order_book_data_source(self) -> OrderBookTrackerDataSource:
        return CoincheckAPIOrderBookDataSource(
            trading_pairs=self._trading_pairs,
            connector=self,
            domain=self.domain,
            api_factory=self._web_assistants_factory)

    def _create_user_stream_data_source(self) -> UserStreamTrackerDataSource:
        return CoincheckAPIUserStreamDataSource(
            auth=self._auth,
            trading_pairs=self._trading_pairs,
            connector=self,
            api_factory=self._web_assistants_factory,
            domain=self.domain,
        )

    def _get_fee(self,
                 base_currency: str,
                 quote_currency: str,
                 order_type: OrderType,
                 order_side: TradeType,
                 amount: Decimal,
                 price: Decimal = s_decimal_NaN,
                 is_maker: Optional[bool] = None) -> TradeFeeBase:
        is_maker = order_type is OrderType.LIMIT_MAKER
        return DeductedFromReturnsTradeFee(percent=self.estimate_fee_pct(is_maker))

    async def _place_order(self,
                           order_id: str,
                           trading_pair: str,
                           amount: Decimal,
                           trade_type: TradeType,
                           order_type: OrderType,
                           price: Decimal,
                           **kwargs) -> Tuple[str, float]:
        order_result = None
        amount_str = f"{amount:f}"
        order_type_str = CONSTANTS.SIDE_BUY if trade_type is TradeType.BUY else CONSTANTS.SIDE_SELL
        pair = await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        api_params = {"rate": "0.00005",
                      "amount": amount_str,
                      "market_buy_amount":None,
                      "order_type": order_type_str,
                      "time_in_force": None,
                      "stop_loss_rate": None,
                      "pair": pair,
                      }
        if order_type == OrderType.LIMIT:
            api_params["time_in_force"] = CONSTANTS.TIME_IN_FORCE_GTC

        try:
            order_result=await self.http_request_coincheck(path_url=CONSTANTS.ORDER_PATH_URL,params=api_params,http_method="POST")
            o_id = str(order_result["id"])
            transact_time = order_result["created_at"]
        except IOError as e:
            error_description = str(e)
            is_server_overloaded = ("status is 503" in error_description
                                    and "Unknown error, please check your request or try again later." in error_description)
            if is_server_overloaded:
                o_id = "UNKNOWN"
                transact_time = self._time_synchronizer.time()
            else:
                raise
        return o_id, transact_time

    async def _place_cancel(self, order_id: str, tracked_order: InFlightOrder):
        try:
            cancel_result=await self.http_request_coincheck(path_url=CONSTANTS.ORDER_PATH_URL,params=order_id,http_method="DELETE")
        except Exception as error:
            self.logger().info(error)
            return False
        if cancel_result.get("success") is True:
            return True
        return False

    async def _format_trading_rules(self, exchange_info_dict: Dict[str, Any]) -> List[TradingRule]:
        trading_pair_rules = exchange_info_dict.get("exchange_status", [])
        retval = []
        for rule in filter(coincheck_utils.is_exchange_information_valid, trading_pair_rules):
            try:
                trading_pair = await self.trading_pair_associated_to_exchange_symbol(symbol=rule.get("pair"))
                filters = rule.get("filters")
                price_filter = [f for f in filters if f.get("filterType") == "PRICE_FILTER"][0]
                lot_size_filter = [f for f in filters if f.get("filterType") == "LOT_SIZE"][0]
                min_notional_filter = [f for f in filters if f.get("filterType") in ["MIN_NOTIONAL", "NOTIONAL"]][0]

                min_order_size = Decimal(lot_size_filter.get("minQty"))
                tick_size = price_filter.get("tickSize")
                step_size = Decimal(lot_size_filter.get("stepSize"))
                min_notional = Decimal(min_notional_filter.get("minNotional"))

                retval.append(
                    TradingRule(trading_pair,
                                min_order_size=min_order_size,
                                min_price_increment=Decimal(tick_size),
                                min_base_amount_increment=Decimal(step_size),
                                min_notional_size=Decimal(min_notional)))

            except Exception:
                self.logger().exception(f"Error parsing the trading pair rule {rule}. Skipping.")
        return retval

    async def _status_polling_loop_fetch_updates(self):
        await self._update_order_fills_from_trades()
        await super()._status_polling_loop_fetch_updates()

    async def _update_trading_fees(self):
        pass

    async def _user_stream_event_listener(self):
        async for event_message in self._iter_user_event_queue():
            try:
                event_type = event_message.get("e")
                if event_type == "executionReport":
                    execution_type = event_message.get("x")
                    if execution_type != "CANCELED":
                        client_order_id = event_message.get("c")
                    else:
                        client_order_id = event_message.get("C")

                    if execution_type == "TRADE":
                        tracked_order = self._order_tracker.all_fillable_orders.get(client_order_id)
                        if tracked_order is not None:
                            fee = TradeFeeBase.new_spot_fee(
                                fee_schema=self.trade_fee_schema(),
                                trade_type=tracked_order.trade_type,
                                percent_token=event_message["N"],
                                flat_fees=[TokenAmount(amount=Decimal(event_message["n"]), token=event_message["N"])]
                            )
                            trade_update = TradeUpdate(
                                trade_id=str(event_message["t"]),
                                client_order_id=client_order_id,
                                exchange_order_id=str(event_message["i"]),
                                trading_pair=tracked_order.trading_pair,
                                fee=fee,
                                fill_base_amount=Decimal(event_message["l"]),
                                fill_quote_amount=Decimal(event_message["l"]) * Decimal(event_message["L"]),
                                fill_price=Decimal(event_message["L"]),
                                fill_timestamp=event_message["T"] * 1e-3,
                            )
                            self._order_tracker.process_trade_update(trade_update)

                    tracked_order = self._order_tracker.all_updatable_orders.get(client_order_id)
                    if tracked_order is not None:
                        order_update = OrderUpdate(
                            trading_pair=tracked_order.trading_pair,
                            update_timestamp=event_message["E"] * 1e-3,
                            new_state=CONSTANTS.ORDER_STATE[event_message["X"]],
                            client_order_id=client_order_id,
                            exchange_order_id=str(event_message["i"]),
                        )
                        self._order_tracker.process_order_update(order_update=order_update)

                elif event_type == "outboundAccountPosition":
                    balances = event_message["B"]
                    for balance_entry in balances:
                        asset_name = balance_entry["a"]
                        free_balance = Decimal(balance_entry["f"])
                        total_balance = Decimal(balance_entry["f"]) + Decimal(balance_entry["l"])
                        self._account_available_balances[asset_name] = free_balance
                        self._account_balances[asset_name] = total_balance

            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger().error("Unexpected error in user stream listener loop.", exc_info=True)
                await self._sleep(5.0)

    async def _update_order_fills_from_trades(self):
        small_interval_last_tick = self._last_poll_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        small_interval_current_tick = self.current_timestamp / self.UPDATE_ORDER_STATUS_MIN_INTERVAL
        long_interval_last_tick = self._last_poll_timestamp / self.LONG_POLL_INTERVAL
        long_interval_current_tick = self.current_timestamp / self.LONG_POLL_INTERVAL

        if (long_interval_current_tick > long_interval_last_tick
                or (self.in_flight_orders and small_interval_current_tick > small_interval_last_tick)):
            query_time = int(self._last_trades_poll_coincheck_timestamp * 1e3)
            self._last_trades_poll_coincheck_timestamp = self._time_synchronizer.time()
            order_by_exchange_id_map = {}
            for order in self._order_tracker.all_fillable_orders.values():
                order_by_exchange_id_map[order.exchange_order_id] = order

            tasks = []
            trading_pairs = self.trading_pairs
            for trading_pair in trading_pairs:
                params = {
                    "pair": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)+"_jpy"
                }
                if self._last_poll_timestamp > 0:
                    params["created_at"] = query_time
                tasks.append(self.http_request_coincheck(
                    path_url=CONSTANTS.MY_TRADES_PATH_URL,
                    params=params))

            self.logger().debug(f"Polling for order fills of {len(tasks)} trading pairs.")
            results = await safe_gather(*tasks, return_exceptions=True)

            for trades, trading_pair in zip(results, trading_pairs):

                if isinstance(trades, Exception):
                    self.logger().network(
                        f"Error fetching trades update for the order {trading_pair}: {trades}.",
                        app_warning_msg=f"Failed to fetch trade update for {trading_pair}."
                    )
                    continue
                for trade in trades:
                    exchange_order_id = str(trade["orderId"])
                    if exchange_order_id in order_by_exchange_id_map:
                        # This is a fill for a tracked order
                        tracked_order = order_by_exchange_id_map[exchange_order_id]
                        fee = TradeFeeBase.new_spot_fee(
                            fee_schema=self.trade_fee_schema(),
                            trade_type=tracked_order.trade_type,
                            percent_token=trade["commissionAsset"],
                            flat_fees=[TokenAmount(amount=Decimal(trade["commission"]), token=trade["commissionAsset"])]
                        )
                        trade_update = TradeUpdate(
                            trade_id=str(trade["id"]),
                            client_order_id=tracked_order.client_order_id,
                            exchange_order_id=exchange_order_id,
                            trading_pair=trading_pair,
                            fee=fee,
                            fill_base_amount=Decimal(trade["qty"]),
                            fill_quote_amount=Decimal(trade["quoteQty"]),
                            fill_price=Decimal(trade["price"]),
                            fill_timestamp=trade["time"] * 1e-3,
                        )
                        self._order_tracker.process_trade_update(trade_update)
                    elif self.is_confirmed_new_order_filled_event(str(trade["id"]), exchange_order_id, trading_pair):
                        # This is a fill of an order registered in the DB but not tracked any more
                        self._current_trade_fills.add(TradeFillOrderDetails(
                            market=self.display_name,
                            exchange_trade_id=str(trade["id"]),
                            symbol=trading_pair))
                        self.trigger_event(
                            MarketEvent.OrderFilled,
                            OrderFilledEvent(
                                timestamp=float(trade["time"]) * 1e-3,
                                order_id=self._exchange_order_ids.get(str(trade["orderId"]), None),
                                trading_pair=trading_pair,
                                trade_type=TradeType.BUY if trade["isBuyer"] else TradeType.SELL,
                                order_type=OrderType.LIMIT_MAKER if trade["isMaker"] else OrderType.LIMIT,
                                price=Decimal(trade["price"]),
                                amount=Decimal(trade["qty"]),
                                trade_fee=DeductedFromReturnsTradeFee(
                                    flat_fees=[
                                        TokenAmount(
                                            trade["commissionAsset"],
                                            Decimal(trade["commission"])
                                        )
                                    ]
                                ),
                                exchange_trade_id=str(trade["id"])
                            ))
                        self.logger().info(f"Recreating missing trade in TradeFill: {trade}")

    async def _all_trade_updates_for_order(self, order: InFlightOrder) -> List[TradeUpdate]:
        trade_updates = []

        if order.exchange_order_id is not None:
            exchange_order_id = int(order.exchange_order_id)
            trading_pair = await self.exchange_symbol_associated_to_pair(trading_pair=order.trading_pair)
            all_fills_response = await self.http_request_coincheck(path_url=CONSTANTS.MY_TRADES_PATH_URL)
            for trade in all_fills_response["transactions"]:
                exchange_order_id = str(trade["id"])
                fee = TradeFeeBase.new_spot_fee(
                    fee_schema=self.trade_fee_schema(),
                    trade_type=order.trade_type,
                    percent_token=trade["commissionAsset"],
                    flat_fees=[TokenAmount(amount=Decimal(trade["commission"]), token=trade["commissionAsset"])]
                )
                trade_update = TradeUpdate(
                    trade_id=str(trade["id"]),
                    client_order_id=order.client_order_id,
                    exchange_order_id=exchange_order_id,
                    trading_pair=trading_pair,
                    fee=fee,
                    fill_base_amount=Decimal(trade["funds"]["jpy"]),
                    fill_quote_amount=Decimal(trade["funds"]["jpy"]),
                    fill_price=Decimal(trade["funds"]["jpy"]),
                    fill_timestamp=trade["created_at"] * 1e-3,
                )
                trade_updates.append(trade_update)

        return trade_updates

    async def _request_order_status(self, tracked_order: InFlightOrder) -> OrderUpdate:
        updated_order_data = await self.http_request_coincheck(path_url=CONSTANTS.ORDER_STATUS)
        order_update = OrderUpdate(
            client_order_id=updated_order_data["orders"][0]["id"],
            exchange_order_id=str(updated_order_data["orders"][0]["id"]),
            trading_pair=updated_order_data["orders"][0]["pair"],
            update_timestamp=updated_order_data["orders"][0]["created_at"] * 1e-3,
            new_state=1,
        )
        return order_update

    async def _update_balances(self):
        balance_info=await self.http_request_coincheck(CONSTANTS.ACCOUNTS_BALANCE_PATH_URL)
        #self.logger().error(balance_info)


        self._account_available_balances.clear()
        self._account_balances.clear()
        if balance_info["success"] != True:
            raise ValueError(f"{balance_info['success']}")

        for coin in balance_info:
            if (float(balance_info[coin]) > 0):
                self.logger().error(f"{coin}:{float(balance_info[coin])}")
                self._account_available_balances[coin] = float(balance_info[coin])
                self._account_balances[coin] = Decimal(balance_info[coin])
                

    def _initialize_trading_pair_symbols_from_exchange_info(self, exchange_info: Dict[str, Any]):
        mapping = bidict()
        for symbol_data in filter(coincheck_utils.is_exchange_information_valid, exchange_info["exchange_status"]):
            current_symbol=str(symbol_data["pair"]).split("_")[0]
            mapping[current_symbol] = combine_to_hb_trading_pair(base=current_symbol,quote="jpy")
        self._set_trading_pair_symbol_map(mapping)

    async def _get_last_traded_price(self, trading_pair: str) -> float:
        params = {
            "pair": await self.exchange_symbol_associated_to_pair(trading_pair=trading_pair)
        }
        resp_json=await self.http_request_coincheck(CONSTANTS.TICKER_PRICE_CHANGE_PATH_URL,params=params)
        return float(resp_json["last"])

