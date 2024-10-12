# zaif_auth.py

import hashlib
import hmac
import time
from typing import Dict
from urllib.parse import urlencode

from hummingbot.core.web_assistant.auth import AuthBase
from hummingbot.core.web_assistant.connections.data_types import RESTRequest, WSRequest


class ZaifAuth(AuthBase):
    def __init__(self, api_key: str, secret_key: str):
        self.api_key: str = api_key
        self.secret_key: str = secret_key
        self._nonce = int(time.time())

    def _get_nonce(self) -> int:
        self._nonce += 1
        return self._nonce

    def get_auth_headers(self, post_data_encoded: str) -> Dict[str, str]:
        sign = hmac.new(
            self.secret_key.encode(),
            post_data_encoded.encode(),
            hashlib.sha512
        ).hexdigest()

        headers = {
            "Key": self.api_key,
            "Sign": sign,
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        return headers

    async def rest_authenticate(self, request: RESTRequest) -> RESTRequest:
        if request.headers is None:
            request.headers = {}

        # Ensure the request method is POST for private API calls
        request.method = 'POST'

        # Initialize POST data if not already set
        if request.data is None:
            request.data = {}

        # 'method' parameter is required in Zaif's private API
        if 'method' not in request.data:
            if request.params and 'method' in request.params:
                request.data['method'] = request.params.pop('method')
            else:
                raise ValueError("Zaif private API requires 'method' parameter in the request data.")

        # Add 'nonce' to the POST data
        request.data['nonce'] = self._get_nonce()

        # URL encode the POST data
        post_data_encoded = urlencode(request.data)

        # Generate authentication headers
        auth_headers = self.get_auth_headers(post_data_encoded)

        # Add authentication headers
        request.headers.update(auth_headers)

        # Set Content-Type header
        request.headers["Content-Type"] = "application/x-www-form-urlencoded"

        # Clear the request params as they are now included in data
        request.params = None


        return request

    async def ws_authenticate(self, request: WSRequest) -> WSRequest:
        return request  # No authentication needed for WebSocket in Zaif

