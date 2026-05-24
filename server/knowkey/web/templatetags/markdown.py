import markdown_it
from django import template
from django.utils.safestring import mark_safe
from mdit_py_plugins import footnote, tasklists

register = template.Library()

# Initialize markdown-it with good defaults
md = markdown_it.MarkdownIt(
    "commonmark",  # or "gfm" if you want GitHub Flavored Markdown
    {
        "html": True,  # Allow raw HTML (careful with user input)
        "linkify": True,
        "typographer": True,
    },
)

# Optional: Add plugins
md.use(footnote.footnote_plugin)
md.use(tasklists.tasklists_plugin)
# md.use(mdit_py_plugins.deflist.deflist_plugin)  # definition lists


@register.filter(name="markdown")
def render_markdown(value):
    """Render markdown and mark as safe for template"""
    if not value:
        return ""

    html = md.render(value)
    return mark_safe(html)
