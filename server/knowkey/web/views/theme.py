from django.conf import settings
from django.http import HttpResponse, HttpResponseRedirect
from django.utils.http import url_has_allowed_host_and_scheme

THEME_QUERY_PARAMETER = "theme"
AVAILABLE_THEMES = getattr(settings, "AVAILABLE_THEMES", ["light", "dark"])


def set_theme(request):
    """
    Redirect to a given URL while setting the chosen theme in a cookie.
    The URL and the theme need to be specified in the request parameters.

    This view changes the site's theme, so it must only be accessed as a POST request.
    If called as a GET request, it redirects to the 'next' parameter without changing state.
    """
    next_url = request.POST.get("next", request.GET.get("next"))
    if (
        next_url or request.accepts("text/html")
    ) and not url_has_allowed_host_and_scheme(
        url=next_url,
        allowed_hosts={request.get_host()},
        require_https=request.is_secure(),
    ):
        next_url = request.META.get("HTTP_REFERER")
        if not url_has_allowed_host_and_scheme(
            url=next_url,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            next_url = "/"
    response = HttpResponseRedirect(next_url) if next_url else HttpResponse(status=204)
    if request.method == "POST":
        theme = request.POST.get(THEME_QUERY_PARAMETER)
        if theme in AVAILABLE_THEMES:
            response.set_cookie(
                settings.THEME_COOKIE_NAME,
                theme,
                max_age=getattr(
                    settings, "THEME_COOKIE_AGE", 365 * 24 * 60 * 60
                ),  # 1 year default
                path=getattr(settings, "THEME_COOKIE_PATH", "/"),
                domain=getattr(settings, "THEME_COOKIE_DOMAIN", None),
                secure=getattr(settings, "THEME_COOKIE_SECURE", False),
                httponly=getattr(settings, "THEME_COOKIE_HTTPONLY", False),
                samesite=getattr(settings, "THEME_COOKIE_SAMESITE", "Lax"),
            )
    return response
