"""conftest.py — Shared fixtures for poker_gpt test suite.

Disables DNS-based email validation during tests so that ``@test.com``
addresses work without network access.
"""

import os

# Disable DNS email checks before auth module is imported
os.environ["NEURALGTO_EMAIL_DNS_CHECK"] = "0"
