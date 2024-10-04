# coincheck_auth.py
import hashlib
import hmac
import time
import urllib
import urllib.parse

from hummingbot.connector.exchange.coincheck.coincheck_constants import PRIVATE_API_VERSION, REST_URL
from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class CoincheckAuth(AuthBase):
    def __init__(self, access_key: str, secret_key: str):
        self.access_key = access_key
        self.secret_key = secret_key
        self._nonce=int(time.time())
    
    def _get_nonce(self) -> str:
        self._nonce += 1
        return str(self._nonce)
    
    def _get_signature(self, message:str):
            signature = hmac.new(
                bytes(self.secret_key.encode()),
                bytes(message.encode()),
                hashlib.sha256
            ).hexdigest()
            return signature
    
    def get_headers(self,request_path:str=""):
        uri=REST_URL+PRIVATE_API_VERSION+request_path
        message=str(self._nonce)+urllib.parse.urlparse(uri).geturl()
        headers = {
            'ACCESS-KEY': self.access_key,
            'ACCESS-NONCE': str(self._nonce),
            'ACCESS-SIGNATURE': self._get_signature(message),
            'Content-Type': 'application/json' 
        }
        return headers

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        """
        Adds the server time and the signature to the request, required for authenticated interactions. It also adds
        the required parameter in the request header.
        :param request: the request to be configured for authenticated interaction
        """
        headers = {}
        if request.headers is not None:
            headers.update(request.headers)
        headers.update(self.get_headers())
        request.headers = headers

        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        """
        This method is intended to configure a websocket request to be authenticated. Coincheck does not use this
        functionality
        """
        return request  # pass-through
