from django import template
from django.utils.safestring import mark_safe

register = template.Library()

ICONS = {
    'bell': ('none', '#C8442A', '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"></path><path d="M13.73 21a2 2 0 0 1-3.46 0"></path>'),
    'check': ('none', '#4A8B5C', '<path d="M20 6 9 17l-5-5"></path>', '2.2'),
    'x': ('none', '#C0392B', '<path d="M18 6 6 18M6 6l12 12"></path>', '2.2'),
    'sparkle': ('#C8442A', None, '<path d="M12 2 13.8 9.2 21 11l-7.2 1.8L12 20l-1.8-7.2L3 11l7.2-1.8Z"></path>'),
    'flag': ('none', '#C8442A', '<path d="M4 15V4a1 1 0 0 1 1-1h11l-2 4 2 4H6a1 1 0 0 0-1 1v7"></path>'),
    'check-circle': ('none', '#4A8B5C', '<circle cx="12" cy="12" r="9"></circle><path d="m9 12 2 2 4-4"></path>'),
    'paperclip': ('none', '#7A6F68', '<path d="M21.4 11.6 12.6 20.4a4 4 0 0 1-5.6-5.6L15.4 6a2.7 2.7 0 0 1 3.8 3.8L10.6 18.4a1.3 1.3 0 0 1-1.8-1.8L16.4 9"></path>'),
    'frown': ('none', '#7A6F68', '<circle cx="12" cy="12" r="9"></circle><path d="M9 10c0-1 .8-1.5 1.5-1.5S12 9 12 10M13 10c0-1 .8-1.5 1.5-1.5S16 9 16 10"></path><path d="M8.5 16c1-1.3 2.2-2 3.5-2s2.5.7 3.5 2"></path>'),
    'mail': ('none', '#C8442A', '<rect x="3" y="5" width="18" height="14" rx="2"></rect><path d="m3 7 9 6 9-6"></path>'),
    'file-edit': ('none', '#C8442A', '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6M9 13h6M9 17h6"></path>'),
    'lightbulb': ('none', '#B8940A', '<path d="M9 18h6M10 22h4"></path><path d="M12 2a6 6 0 0 0-4 10.5c.6.6 1 1.4 1 2.5h6c0-1.1.4-1.9 1-2.5A6 6 0 0 0 12 2Z"></path>'),
    'celebrate': ('none', '#C8442A', '<path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"></path><circle cx="12" cy="12" r="4"></circle>'),
    'target': ('none', '#C8442A', '<circle cx="12" cy="12" r="9"></circle><circle cx="12" cy="12" r="5"></circle><circle cx="12" cy="12" r="1"></circle>'),
    'map': ('none', '#C8442A', '<path d="M9 4 3 6v14l6-2 6 2 6-2V4l-6 2-6-2Z"></path><path d="M9 4v14M15 6v14"></path>'),
    'bar-chart': ('none', '#C8442A', '<path d="M3 3v18h18"></path><path d="M7 15v3M12 10v8M17 6v12"></path>'),
    'play-circle': ('none', '#C8442A', '<circle cx="12" cy="12" r="10"></circle><path d="m10 8 6 4-6 4Z"></path>'),
    'book-open': ('none', '#C8442A', '<path d="M12 4a4 4 0 0 0-4-2H4v15h5a3 3 0 0 1 3 2"></path><path d="M12 4a4 4 0 0 1 4-2h4v15h-5a3 3 0 0 0-3 2"></path>'),
    'book': ('none', '#C8442A', '<path d="M4 19.5A2.5 2.5 0 0 1 6.5 17H20"></path><path d="M6.5 2H20v20H6.5A2.5 2.5 0 0 1 4 19.5v-15A2.5 2.5 0 0 1 6.5 2Z"></path>'),
    'refresh': ('none', '#7A6F68', '<path d="M21 12a9 9 0 1 1-3-6.7"></path><path d="M21 4v5h-5"></path>'),
    'trash': ('none', '#C0392B', '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2m3 0-1 14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2L4 6"></path><path d="M10 11v6M14 11v6"></path>'),
    'pencil': ('none', '#7A6F68', '<path d="M17 3a2.85 2.85 0 1 1 4 4L7.5 20.5 2 22l1.5-5.5Z"></path><path d="m15 5 4 4"></path>'),
    'user': ('none', '#C8442A', '<circle cx="12" cy="8" r="4"></circle><path d="M4 21c0-4 3.6-7 8-7s8 3 8 7"></path>'),
    'clipboard': ('none', '#C8442A', '<rect x="6" y="4" width="12" height="17" rx="1.5"></rect><path d="M9 4V3a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v1M9 11h6M9 15h6"></path>'),
    'file-text': ('none', '#7A6F68', '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path><path d="M14 2v6h6M9 13h6M9 17h6"></path>'),
    'graduation-cap': ('none', '#C8442A', '<path d="M22 10 12 5 2 10l10 5 10-5Z"></path><path d="M6 12v5c0 1.5 2.7 3 6 3s6-1.5 6-3v-5"></path>'),
    'star': ('#C8442A', None, '<path d="m12 2 2.9 6.3 6.9.9-5 4.8 1.3 6.9L12 17.3 5.9 20.9l1.3-6.9-5-4.8 6.9-.9Z"></path>'),
    'heart': ('none', '#C8442A', '<path d="M12 21s-7-4.5-9.5-9C1 8.5 2 5 5.5 5c2 0 3.3 1.2 4 2.3.7-1.1 2-2.3 4-2.3 3.5 0 4.5 3.5 3 7-2.5 4.5-9.5 9-9.5 9Z"></path>'),
}


@register.simple_tag
def icon(name, size=18, color=None):
    """
    Использование в шаблонах:
    {% load icons %}
    {% icon 'bell' %}
    {% icon 'check-circle' size=24 %}
    {% icon 'trash' color='#fff' %}
    """
    data = ICONS.get(name)
    if not data:
        return ''
    fill = data[0]
    stroke = data[1]
    paths = data[2]
    stroke_width = data[3] if len(data) > 3 else '1.8'

    fill_attr = color if fill != 'none' else 'none'
    stroke_attr = color if color and fill == 'none' else stroke

    if fill == 'none':
        svg = (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" '
            f'stroke="{stroke_attr}" stroke-width="{stroke_width}" '
            f'stroke-linecap="round" stroke-linejoin="round" style="vertical-align: middle;">{paths}</svg>'
        )
    else:
        svg = (
            f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" '
            f'fill="{color or fill}" style="vertical-align: middle;">{paths}</svg>'
        )
    return mark_safe(svg)