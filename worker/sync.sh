#!/bin/sh
# Copy the API modules into the Worker bundle. The Worker only needs these two
# files (not the scraper and its PDF libraries). A test checks the copies are current.
set -e
cd "$(dirname "$0")"
mkdir -p src/rbz_rates
: > src/rbz_rates/__init__.py
cp ../rbz_rates/api.py ../rbz_rates/access.py src/rbz_rates/
