# -*- coding: utf-8 -*-

"""Software version of BEL Commons."""

__all__ = [
    'VERSION',
    'get_version',
]

VERSION = '0.3.2-dev'


def get_version() -> str:
    """Get the current BEL Commons version string."""
    return VERSION
