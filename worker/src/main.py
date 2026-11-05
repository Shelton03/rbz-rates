"""Cloudflare Workers entrypoint. The API lives in ../rbz_rates/ at the repo root;
src/rbz_rates/ is a copy of the modules it needs, refreshed by ./sync.sh (CI runs it before deploy)."""
from workers import asgi

from rbz_rates.api import app

Default = asgi.entrypoint(app)
