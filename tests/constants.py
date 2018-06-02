# -*- coding: utf-8 -*-

"""Test constants for PyBEL Web."""

import logging
import os

__all__ = [
    'dir_path',
    'test_bel_pickle_path',
]

log = logging.getLogger(__name__)

dir_path = os.path.dirname(os.path.realpath(__file__))

test_bel_pickle_path = os.path.join(dir_path, 'test_bel.gpickle')

TEST_CONNECTION = os.environ.get('PYBEL_TEST_CONNECTION')
