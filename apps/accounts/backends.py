"""
Custom Social Auth OAuth2 backend for VATSIM Connect.
"""

import requests as _requests
from social_core.backends.oauth import BaseOAuth2


_BASE_URL = "https://auth.vatsim.net"


class VATSIMOAuth2(BaseOAuth2):
    name = "vatsim"

    AUTHORIZATION_URL = f"{_BASE_URL}/oauth/authorize"
    ACCESS_TOKEN_URL = f"{_BASE_URL}/oauth/token"
    REFRESH_TOKEN_URL = f"{_BASE_URL}/oauth/token"
    API_URL = f"{_BASE_URL}/api/user"

    ACCESS_TOKEN_METHOD = "POST"
    SCOPE_SEPARATOR = " "
    REDIRECT_STATE = False
    STATE_PARAMETER = False
    DEFAULT_SCOPE = ["full_name", "vatsim_details", "email", "country"]

    def user_data(self, access_token, *args, **kwargs):
        resp = _requests.get(
            self.API_URL,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json()

    def get_user_id(self, details, response):
        return str(response.get("data", {}).get("cid", ""))

    def get_user_details(self, response):
        data = response.get("data", {})
        personal = data.get("personal", {})
        vatsim = data.get("vatsim", {})
        rating_obj = vatsim.get("rating", {})

        full_name = (
            f"{personal.get('name_first', '')} {personal.get('name_last', '')}".strip()
        )
        return {
            "cid": data.get("cid"),
            "username": str(data.get("cid", "")),
            "email": personal.get("email", ""),
            "vatsim_name": full_name,
            "fullname": full_name,
            "rating": rating_obj.get("id", 1),
        }
