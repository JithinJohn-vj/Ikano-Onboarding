"""Local-only request adaptations for the embedded development browser."""


class LocalNullOriginCsrfMiddleware:
    """Allow token-validated requests from the desktop browser's opaque origin.

    The embedded browser sends ``Origin: null`` even when it is displaying the
    loopback development server. Django rejects that before checking the CSRF
    token. We remove only this opaque origin, only for loopback hosts, so the
    normal CSRF-token validation still applies and production hosts are not
    affected.
    """

    loopback_hosts = {"127.0.0.1", "localhost"}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":", 1)[0]
        if request.META.get("HTTP_ORIGIN") == "null" and host in self.loopback_hosts:
            request.META.pop("HTTP_ORIGIN", None)
        return self.get_response(request)
