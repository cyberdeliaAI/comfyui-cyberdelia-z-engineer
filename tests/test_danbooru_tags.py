import importlib.util
from pathlib import Path
import sys
import unittest

from _requests_stub import ensure_requests

ensure_requests()


ROOT = Path(__file__).resolve().parents[1]
PACKAGE_NAME = "cyberdelia_z_engineer_test_package"
if PACKAGE_NAME not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        PACKAGE_NAME,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    package = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE_NAME] = package
    spec.loader.exec_module(package)

tags_module = sys.modules[f"{PACKAGE_NAME}.danbooru_tags"]


class DanbooruTagTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = tags_module.get_tag_db()

    def test_bundled_database_loads(self):
        self.assertEqual(len(self.database), 140782)

    def test_normalize_and_both_output_formats(self):
        self.assertEqual(tags_module.normalize_tag(" Blue  Eyes "), "blue_eyes")
        self.assertEqual(tags_module.format_tag("blue_eyes", "spaces"), "blue eyes")
        self.assertEqual(
            tags_module.format_tag("blue_eyes", "underscores"),
            "blue_eyes",
        )
        self.assertEqual(tags_module.format_tag(">_<", "spaces"), ">_<")

    def test_aliases_and_word_forms_are_resolved(self):
        self.assertEqual(self.database.resolve("blonde"), "blonde_hair")
        self.assertEqual(self.database.resolve("smirking"), "smirk")
        self.assertEqual(self.database.resolve("silver hair"), "grey_hair")
        self.assertEqual(self.database.resolve("blue eye"), "blue_eyes")

    def test_strict_validation_reports_unknown_candidates(self):
        prompt, kept, dropped = self.database.validate(
            "1girl, utter nonsense qzx, beach",
            strict=True,
        )
        self.assertEqual(prompt, "1girl, beach")
        self.assertEqual(kept, ["1girl", "beach"])
        self.assertEqual(dropped, ["utter nonsense qzx"])

    def test_underscore_output_and_danbooru_sorting(self):
        prompt, kept, dropped = self.database.validate(
            "night, hatsune miku, 1girl, blue eyes",
            sort_tags=True,
            tag_format="underscores",
        )
        self.assertEqual(
            prompt,
            "1girl, hatsune_miku, night, blue_eyes",
        )
        self.assertEqual(kept, prompt.split(", "))
        self.assertEqual(dropped, [])

    def test_subphrase_recovery_is_visible_and_deterministic(self):
        prompt, kept, dropped = self.database.validate("black crop top")
        self.assertEqual(prompt, "crop top")
        self.assertEqual(kept, ["crop top"])
        self.assertEqual(dropped, ["black crop top"])

    def test_non_strict_mode_keeps_an_unknown_compound_intact(self):
        prompt, kept, dropped = self.database.validate(
            "black crop top",
            strict=False,
            tag_format="underscores",
        )
        self.assertEqual(prompt, "black_crop_top")
        self.assertEqual(kept, ["black_crop_top"])
        self.assertEqual(dropped, [])

    def test_tag_limit_reports_candidates_that_did_not_fit(self):
        prompt, kept, dropped = self.database.validate(
            "1girl, beach, smile",
            max_tags=1,
        )
        self.assertEqual(prompt, "1girl")
        self.assertEqual(kept, ["1girl"])
        self.assertEqual(dropped, ["beach", "smile"])

    def test_category_names_and_codes_are_parsed(self):
        self.assertEqual(
            tags_module.parse_categories("artist, meta, 4"),
            {1, 5, 4},
        )

    def test_invalid_output_format_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "tag_format"):
            self.database.validate("1girl", tag_format="hyphens")


if __name__ == "__main__":
    unittest.main()
