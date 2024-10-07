from typing import Any, Dict

from pydantic import Field, SecretStr

from hummingbot.client.config.config_data_types import BaseConnectorConfigMap, ClientFieldData

CENTRALIZED = True

def is_exchange_information_valid(exchange_info: Dict[str, Any]) -> bool:
    # is_spot = True
    # is_trading = False
    # if exchange_info.get("status", None) == "available":
    #     is_trading = True
    # return is_trading and is_spot
    return (
        exchange_info['status'] == 'available' and
        exchange_info['availability']['market_order'] and
        exchange_info['availability']['order']
    )

class CoincheckConfigMap(BaseConnectorConfigMap):
    connector: str = Field(default="coincheck", const=True, client_data=None)
    coincheck_api_key: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your coincheck API key",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )
    coincheck_api_secret: SecretStr = Field(
        default=...,
        client_data=ClientFieldData(
            prompt=lambda cm: "Enter your coincheck API secret",
            is_secure=True,
            is_connect_key=True,
            prompt_on_new=True,
        )
    )

    class Config:
        title = "coincheck"

KEYS = CoincheckConfigMap.construct()
