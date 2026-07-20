import sys
import types
import unittest
from unittest.mock import patch

from vision_utils import (
    DEFAULT_VISION_INSTRUCTION,
    build_vision_user_content,
    image_to_data_url,
)


class FakeArray:
    ndim = 3
    shape = (1000, 2000, 3)


class FakeFrame:
    def detach(self):
        return self

    def cpu(self):
        return self

    def clamp(self, _minimum, _maximum):
        return self

    def __mul__(self, _value):
        return self

    def round(self):
        return self

    def byte(self):
        return self

    def numpy(self):
        return FakeArray()


class FakeTensor:
    ndim = 4

    def __getitem__(self, index):
        if index != 0:
            raise IndexError(index)
        return FakeFrame()


class FakePilImage:
    size = (2000, 1000)
    mode = "RGB"

    def __init__(self):
        self.thumbnail_args = None

    def thumbnail(self, size, resampling):
        self.thumbnail_args = (size, resampling)

    def convert(self, mode):
        self.mode = mode
        return self

    def save(self, buffer, **_kwargs):
        buffer.write(b"encoded-image")


class VisionUtilsTests(unittest.TestCase):
    def test_empty_text_uses_default_image_to_prompt_instruction(self):
        content = build_vision_user_content("", "data:image/jpeg;base64,abc")
        self.assertEqual(content[0], {"type": "text", "text": DEFAULT_VISION_INSTRUCTION})
        self.assertEqual(content[1]["type"], "image_url")

    def test_text_is_added_as_direction_not_replaced(self):
        content = build_vision_user_content(
            "Focus on the clothing.",
            "data:image/png;base64,abc",
        )
        self.assertIn(DEFAULT_VISION_INSTRUCTION, content[0]["text"])
        self.assertIn("Focus on the clothing.", content[0]["text"])

    def test_comfy_tensor_is_encoded_as_resized_data_url(self):
        fake_pil_module = types.ModuleType("PIL")
        fake_image = FakePilImage()

        class FakeImageFactory:
            Resampling = types.SimpleNamespace(LANCZOS="lanczos")

            @staticmethod
            def fromarray(array):
                self.assertIsInstance(array, FakeArray)
                return fake_image

        fake_pil_module.Image = FakeImageFactory
        with patch.dict(sys.modules, {"PIL": fake_pil_module}):
            result = image_to_data_url(FakeTensor())

        self.assertEqual(
            result,
            "data:image/jpeg;base64,ZW5jb2RlZC1pbWFnZQ==",
        )
        self.assertEqual(fake_image.thumbnail_args, ((1536, 1536), "lanczos"))


if __name__ == "__main__":
    unittest.main()
