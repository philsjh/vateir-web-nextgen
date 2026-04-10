"""
Endpoint registry for auto-generated API documentation.
"""

_ENDPOINTS = []


def api_endpoint(path, method="GET", summary="", description="", params=None, response_example=None):
    """Decorator that registers an endpoint for documentation."""
    def decorator(view_func):
        _ENDPOINTS.append({
            "path": path,
            "method": method,
            "summary": summary,
            "description": description,
            "params": params or [],
            "response_example": response_example,
            "view_name": view_func.__name__,
        })
        return view_func
    return decorator


def get_registered_endpoints():
    return sorted(_ENDPOINTS, key=lambda e: e["path"])
