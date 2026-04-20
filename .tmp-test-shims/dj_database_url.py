from urllib.parse import urlparse


def config(default=None, conn_max_age=0, **kwargs):
    url = default
    if not url:
        return {}
    parsed = urlparse(url)
    if parsed.scheme != 'sqlite':
        raise ValueError(f'Unsupported database URL in test shim: {url}')
    name = parsed.path or ''
    if name.startswith('/') and not name.startswith('//'):
        name = name[1:]
    return {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': name or ':memory:',
        'CONN_MAX_AGE': conn_max_age,
    }
