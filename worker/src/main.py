"""Cloudflare Workers entrypoint. The API itself lives in rbz_rates/api.py;
rbz_api.py next to this file is a copy of it, refreshed by `make sync` / CI before deploy."""
from workers import asgi

from rbz_api import app

Default = asgi.entrypoint(app)
