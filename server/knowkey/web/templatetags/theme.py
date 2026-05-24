from django import template
from django.conf import settings

register = template.Library()


@register.inclusion_tag("web/components/theme_selector.html", takes_context=True)
def theme_selector(context):
    """
    Renders a theme selector form with available themes.
    """
    request = context["request"]
    current_theme = request.COOKIES.get(
        settings.THEME_COOKIE_NAME, getattr(settings, "AVAILABLE_THEMES", ["light"])[0]
    )
    return {
        "themes": getattr(settings, "AVAILABLE_THEMES", ["light", "dark"]),
        "current_theme": current_theme,
        "next_url": request.path,
    }


@register.simple_tag(takes_context=True)
def get_current_theme(context):
    """
    Returns the current theme from the cookie or defaults to the first available theme.
    """
    request = context["request"]
    theme = request.COOKIES.get(settings.THEME_COOKIE_NAME)
    if theme in getattr(settings, "AVAILABLE_THEMES", ["light", "dark"]):
        return theme
    return getattr(settings, "AVAILABLE_THEMES", ["light", "dark"])[0]


@register.simple_tag
def get_available_themes():
    """
    Returns the list of available themes.
    """
    return getattr(settings, "AVAILABLE_THEMES", ["light", "dark"])
