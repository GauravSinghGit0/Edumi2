"""
accounts/middleware.py
Centralized Identity Middleware.
Attaches the canonical Single Source of Truth `request.identity` dictionary to every incoming HTTP request.
"""

from accounts.identity import IdentityService


class CentralizedIdentityMiddleware:
    """
    Middleware that populates `request.identity` as the canonical SSOT identity dictionary.
    """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if hasattr(request, 'user'):
            request.identity = IdentityService.get_identity(request.user)
        else:
            request.identity = IdentityService.get_identity(None)

        response = self.get_response(request)
        return response
