"""
API key authentication for the VATéir API.

Supports API key via:
  - Header: Authorization: Bearer vateir_...
  - Header: X-API-Key: vateir_...
  - Query parameter: ?api_key=vateir_...
"""

import functools
import json

from django.http import JsonResponse

from .models import APIKey


def _extract_api_key(request):
    """Extract the API key from the request."""
    # 1. Authorization: Bearer <key>
    auth_header = request.META.get("HTTP_AUTHORIZATION", "")
    if auth_header.startswith("Bearer "):
        return auth_header[7:].strip()

    # 2. X-API-Key header
    api_key_header = request.META.get("HTTP_X_API_KEY", "")
    if api_key_header:
        return api_key_header.strip()

    # 3. Query parameter
    return request.GET.get("api_key", "").strip()


def require_api_key(view_func):
    """Decorator that requires a valid API key for access."""
    @functools.wraps(view_func)
    def wrapped(request, *args, **kwargs):
        raw_key = _extract_api_key(request)
        if not raw_key:
            return JsonResponse(
                {"error": "Authentication required. Provide an API key via Authorization header, X-API-Key header, or api_key query parameter."},
                status=401,
            )

        api_key = APIKey.authenticate(raw_key)
        if api_key is None:
            return JsonResponse(
                {"error": "Invalid or expired API key."},
                status=403,
            )

        request.api_key = api_key
        return view_func(request, *args, **kwargs)
    return wrapped
