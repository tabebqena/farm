"""Discovery shim for :class:`CoverageManifestTest`.

Django's test runner only discovers modules matching ``test*.py``, so the
``CoverageManifestTest`` class — defined in ``apps/app_operation/tests/base.py``
per the plan — is re-exported here so ``manage.py test`` actually runs it.

The class body, the ``COVERAGE_MANIFEST`` data and the resolution helper all
live in ``base.py``; this module only makes the class discoverable.
"""
from .base import CoverageManifestTest  # noqa: F401

__all__ = ["CoverageManifestTest"]
