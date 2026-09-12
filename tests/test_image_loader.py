import importlib.util
from pathlib import Path
import sys
import tempfile
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

package = sys.modules[PACKAGE_NAME]
image_loader = sys.modules[f"{PACKAGE_NAME}.image_loader"]


class ImageLoaderTests(unittest.TestCase):
    def test_node_is_registered(self):
        self.assertIs(
            package.NODE_CLASS_MAPPINGS["CyberdeliaVisionImageLoader"],
            image_loader.CyberdeliaVisionImageLoader,
        )
        self.assertEqual(
            package.NODE_DISPLAY_NAME_MAPPINGS["CyberdeliaVisionImageLoader"],
            "Cyberdelia Vision Image Loader",
        )

    def test_lists_supported_images_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "b.JPG").write_bytes(b"image")
            (root / "notes.txt").write_text("ignore", encoding="utf-8")
            (root / "nested").mkdir()
            (root / "nested" / "a.png").write_bytes(b"image")

            self.assertEqual(
                image_loader.list_input_images(root),
                ["b.JPG", "nested/a.png"],
            )

    def test_resolve_accepts_input_annotation_and_rejects_escape(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "selected.png"
            image.write_bytes(b"image")

            self.assertEqual(
                image_loader.resolve_input_image(root, "selected.png [input]"),
                image.resolve(),
            )
            with self.assertRaises(ValueError):
                image_loader.resolve_input_image(root, "../outside.png", False)

    def test_delete_removes_only_selected_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            selected = root / "selected.png"
            retained = root / "retained.png"
            selected.write_bytes(b"selected")
            retained.write_bytes(b"retained")

            deleted = image_loader.delete_input_image(root, "selected.png")

            self.assertEqual(deleted, "selected.png")
            self.assertFalse(selected.exists())
            self.assertTrue(retained.exists())

    def test_resize_preserves_proportion_and_never_upscales(self):
        self.assertEqual(
            image_loader.resized_dimensions(2304, 3072, 1024),
            (768, 1024),
        )
        self.assertEqual(
            image_loader.resized_dimensions(400, 300, 1024),
            (400, 300),
        )
        self.assertEqual(
            image_loader.resized_dimensions(2304, 3072, None),
            (2304, 3072),
        )

    def test_vision_size_options_are_validated(self):
        self.assertEqual(
            image_loader.max_dimension_from_option("1536 max (recommended)"),
            1536,
        )
        self.assertIsNone(image_loader.max_dimension_from_option("original"))
        with self.assertRaises(ValueError):
            image_loader.max_dimension_from_option("4096")


if __name__ == "__main__":
    unittest.main()
