# -*- coding: utf-8 -*-

"""Test constants for BEL Commons."""

import logging
import os

__all__ = [
    'dir_path',
]

log = logging.getLogger(__name__)

dir_path = os.path.dirname(os.path.realpath(__file__))
