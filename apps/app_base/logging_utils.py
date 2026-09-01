"""Shared logging handles for the Farm project.

One project-wide logger plus a dedicated compliance/audit channel.
Both are configured in ``farm/settings.py`` LOGGING.
"""

import logging

# One logger for the whole project. Configured at INFO by default so
# ``logger.debug(...)`` calls stay silent unless tracing is enabled.
logger = logging.getLogger("farm")

# Compliance-only channel, routed to ``logs/audit.log``.
# Used for create/update/delete of key records, reversals, and period close.
audit_logger = logging.getLogger("farm_audit")
