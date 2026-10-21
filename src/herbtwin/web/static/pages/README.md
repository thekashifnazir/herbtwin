One small stylesheet per page group (`home.css`, `answer.css`, ...). `style.py` appends them
after `herbtwin.css` in name order and inlines the lot into every page. Use the tokens
(`var(--primary)` etc.) from `herbtwin.css`; never a raw colour.

Every sheet is inlined into every page, so every rule must start with its page's class:
the page sets `{% block page %}answer-page{% endblock %}` (it lands on `<body>`) and
`answer.css` writes `.answer-page .lead { … }`, never a bare `.lead`.

## The frame: reading column, wide pages, two columns

The header, footer and `main .wrap` share one 72rem frame (`--frame`), so the wordmark and
nav never move between pages. By default `main .wrap` holds a 38rem reading column
(`--measure`) at the frame's left edge. A page that needs the room adds ` wide` to it:

```jinja
{% block wrap %} wide{% endblock %}   {# <main><div class="wrap wide"> #}
```

Inside a wide page, `.cols` is the two-column helper: one column on phones; at 960px and
up the first child is the main column (`1fr`) and the second, usually an `<aside>`, a
22rem side column beside it, both top-aligned.

```html
<div class="cols"><div>…the answer…</div><aside>…evidence, chat…</aside></div>
```

## The nav

`{% from "_nav.html" import site_nav %}` then `{{ site_nav(person, accounts, here) }}` in
your `{% block nav %}`, or leave the block out and base.html calls it for you. Anything you
don't pass is read from the request (spot switch, accounts, the page you're on, and, when
the page has no `person` or `signed_in`, a session-cookie hint). Signed out, it never links
to `/plants`.
