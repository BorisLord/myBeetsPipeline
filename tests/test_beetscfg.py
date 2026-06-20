import unittest

from gbc.beetscfg import BeetsImport, parse_import


class TestBeetsImport(unittest.TestCase):
    def test_move_consumes_source(self):
        bi = BeetsImport(move=True)
        self.assertTrue(bi.source_consumed)
        self.assertFalse(bi.source_preserved)
        self.assertFalse(bi.clean_independent)
        self.assertEqual(bi.label, "move")

    def test_copy_preserves_and_is_independent(self):
        bi = BeetsImport(copy=True)
        self.assertTrue(bi.source_preserved)
        self.assertTrue(bi.clean_independent)
        self.assertEqual(bi.label, "copy")

    def test_copy_plus_delete_consumes(self):
        bi = BeetsImport(copy=True, delete=True)
        self.assertTrue(bi.source_consumed)
        self.assertFalse(bi.clean_independent)        # consumed -> nothing to reclaim
        self.assertEqual(bi.label, "delete")

    def test_symlink_preserved_but_not_independent(self):
        bi = BeetsImport(link=True)
        self.assertTrue(bi.source_preserved)
        self.assertFalse(bi.clean_independent)        # clean would dangle if the source moved
        self.assertEqual(bi.label, "link")

    def test_reflink_and_hardlink_are_independent(self):
        self.assertTrue(BeetsImport(reflink=True).clean_independent)
        self.assertTrue(BeetsImport(hardlink=True).clean_independent)

    def test_inplace_preserved_but_not_independent(self):
        bi = BeetsImport()
        self.assertTrue(bi.source_preserved)
        self.assertFalse(bi.clean_independent)        # clean == source file; reclaim would break the lib
        self.assertEqual(bi.label, "in-place")


class TestParseImport(unittest.TestCase):
    def test_yaml_yes_no(self):
        bi = parse_import("import:\n  move: yes\n  copy: no\n")
        self.assertTrue(bi.move)
        self.assertFalse(bi.copy)

    def test_yaml_true_false_copy(self):
        bi = parse_import("import:\n  move: false\n  copy: true\n")
        self.assertFalse(bi.move)
        self.assertTrue(bi.copy)
        self.assertTrue(bi.clean_independent)

    def test_string_values_coerced(self):
        bi = parse_import("import:\n  move: 'no'\n  hardlink: 'yes'\n")
        self.assertFalse(bi.move)
        self.assertTrue(bi.hardlink)

    def test_reflink_auto_is_truthy(self):
        bi = parse_import("import:\n  reflink: auto\n")        # beets' documented 'auto' value
        self.assertTrue(bi.reflink)
        self.assertTrue(bi.clean_independent)
        self.assertEqual(bi.label, "reflink")

    def test_missing_import_block(self):
        self.assertEqual(parse_import("directory: /x\n"), BeetsImport())

    def test_garbage_is_safe(self):
        self.assertIsInstance(parse_import(":::not: yaml: ["), BeetsImport)


if __name__ == "__main__":
    unittest.main()
