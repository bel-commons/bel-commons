import unittest

from pybel_web.mozg_service_utils import get_rc_tree_annotations, build_annotation_search_filter

class TestMozgUtils(unittest.TestCase):
    def test_filter_1(self):
        f1 = build_annotation_search_filter(
            annotations=[],
            values=[]
        )

        ...


        self.assertEqual()

