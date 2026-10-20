import hashlib
from functools import lru_cache

from django.contrib.staticfiles import finders


@lru_cache(maxsize=None)
def _asset_version(path: str) -> str:
    """Short content hash of a static file. Hosts like Vercel give every file
    the same Last-Modified date, so browsers revalidate a changed stylesheet
    as "not modified"; putting the hash in the URL makes each change a new
    URL instead."""
    location = finders.find(path)
    if not location:
        return ""
    with open(location, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:12]


def static_versions(request):
    return {"STYLE_VERSION": _asset_version("onboarding/style.css")}
