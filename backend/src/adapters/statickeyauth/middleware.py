"""StaticKeyAuth — API key validation + anonymous CIDR bypass.

Ported from Go server/modules/statickeyauth/statickeyauthimpl.go.
"""

from __future__ import annotations

import ipaddress
import logging

from fastapi import HTTPException, Request

from src.shared.context import AGENT_ID, RequestContext

logger = logging.getLogger(__name__)


class StaticKeyAuth:
    def __init__(self, api_key: str, anonymous_cidr: str) -> None:
        self.api_key = api_key
        self.anonymous_cidr = anonymous_cidr

        if anonymous_cidr == "*":
            self._skip_cidr_check = True
            self._network: ipaddress.IPv4Network | ipaddress.IPv6Network | None = None
            logger.warning("Bypassing all anonymous CIDR traffic checks. Dev use only.")
        else:
            self._skip_cidr_check = False
            self._network = ipaddress.ip_network(anonymous_cidr, strict=False)

    def validate_api_key(self, key: str) -> bool:
        if not key:
            return False
        pieces = key.split(" ")
        return pieces[-1] == self.api_key

    def validate_authorization(self, key: str, ip_str: str) -> bool:
        if key and not key.startswith("Bearer "):
            return self.validate_api_key(key)

        if self._skip_cidr_check:
            return True

        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            return False

        assert self._network is not None
        return addr in self._network

    async def __call__(self, request: Request) -> RequestContext:
        key = request.headers.get("Authorization", "")
        ip_str = request.client.host if request.client else "0.0.0.0"

        if not self.validate_authorization(key, ip_str):
            raise HTTPException(status_code=401, detail="Access denied")

        return RequestContext(requestor_id=AGENT_ID, username="agent")
