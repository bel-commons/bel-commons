# -*- coding: utf-8 -*-

import unittest

from pybel.constants import ANNOTATIONS
from pybel_web.mozg_service import _annotation_dict_filter_helper


class TestMozgFilter(unittest.TestCase):
    def test_no_annotation(self):
        example = {}
        self.assertFalse(_annotation_dict_filter_helper(example, [], []))

    def test_annotation_missing(self):
        example = {
            ANNOTATIONS: {
                'MeSHAnatomy': 'dorsal thingy'
            }
        }
        self.assertFalse(_annotation_dict_filter_helper(example, ['Uberon'], ['hypothalamus']))

    def test_annotation_mismatch(self):
        example = {
            ANNOTATIONS: {
                'MeSHAnatomy': 'hypothalamus'
            }
        }
        self.assertFalse(_annotation_dict_filter_helper(example, ['Uberon'], ['hypothalamus']))

    def test_annotation_match(self):
        example = {
            ANNOTATIONS: {
                'MeSHAnatomy': 'hypothalamus'
            }
        }
        self.assertTrue(_annotation_dict_filter_helper(example, ['Uberon', 'MeSHAnatomy'], ['hypothalamus']))

    def test_annotation_match_with_irrelevant_1(self):
        example = {
            ANNOTATIONS: {
                'MeSHAnatomy': 'hypothalamus',
                'dummy': 'dorsal thingy'
            }
        }
        self.assertTrue(_annotation_dict_filter_helper(
            example,
            ['Uberon', 'MeSHAnatomy'],
            ['hypothalamus', 'dorsal thingy']
        ))

    def test_annotation_double_match(self):
        example = {
            ANNOTATIONS: {
                'MeSHAnatomy': 'hypothalamus',
                'Uberon': 'dorsal thingy'
            }
        }
        self.assertTrue(_annotation_dict_filter_helper(
            example,
            ['Uberon', 'MeSHAnatomy'],
            ['hypothalamus', 'dorsal thingy']
        ))
