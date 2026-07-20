import unittest
from unittest.mock import Mock, patch

from _requests_stub import ensure_requests

requests = ensure_requests()

import model_utils


class ModelUtilsTests(unittest.TestCase):
    def setUp(self):
        model_utils.clear_model_cache()

    def test_normalize_openai_base_url(self):
        self.assertEqual(
            model_utils.normalize_openai_base_url("http://localhost:1234"),
            "http://localhost:1234/v1",
        )
        self.assertEqual(
            model_utils.normalize_openai_base_url(
                "http://localhost:1234/v1/chat/completions"
            ),
            "http://localhost:1234/v1",
        )

    @patch("model_utils.requests.get")
    def test_native_discovery_filters_embeddings_and_sorts_loaded_first(self, get):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "models": [
                {"key": "model-b", "type": "llm", "loaded_instances": []},
                {
                    "key": "embed-a",
                    "type": "embedding",
                    "loaded_instances": [{"id": "embed-a"}],
                },
                {
                    "key": "model-a",
                    "type": "llm",
                    "capabilities": {"vision": True},
                    "loaded_instances": [{"id": "model-a@loaded"}],
                },
            ]
        }
        get.return_value = response

        models = model_utils.discover_models("http://localhost:1234/v1")

        self.assertEqual([model["id"] for model in models], ["model-a", "model-b"])
        self.assertTrue(models[0]["loaded"])
        self.assertTrue(models[0]["vision"])
        self.assertFalse(models[1]["vision"])
        get.assert_called_once_with("http://localhost:1234/api/v1/models", timeout=2.0)

    @patch("model_utils.requests.get")
    def test_discovery_falls_back_to_openai_models(self, get):
        fallback = Mock()
        fallback.raise_for_status.return_value = None
        fallback.json.return_value = {"data": [{"id": "generic-model"}]}
        get.side_effect = [requests.exceptions.ConnectionError("offline"), fallback]

        models = model_utils.discover_models("http://example.test/v1")

        self.assertEqual(models[0]["id"], "generic-model")
        self.assertEqual(models[0]["source"], "openai")

    @patch("model_utils.discover_models")
    def test_auto_prefers_the_only_loaded_model(self, discover):
        discover.return_value = [
            {"id": "one", "loaded": False},
            {"id": "two", "loaded": True},
        ]
        self.assertEqual(
            model_utils.resolve_model_name("auto", "http://localhost:1234/v1"),
            "two",
        )

    @patch("model_utils.discover_models")
    def test_auto_rejects_ambiguous_loaded_models(self, discover):
        discover.return_value = [
            {"id": "one", "loaded": True},
            {"id": "two", "loaded": True},
        ]
        with self.assertRaisesRegex(model_utils.ModelDiscoveryError, "multiple LLMs"):
            model_utils.resolve_model_name("auto", "http://localhost:1234/v1")

    @patch("model_utils.discover_models")
    def test_auto_vision_ignores_loaded_text_only_model(self, discover):
        discover.return_value = [
            {"id": "text-only", "loaded": True, "vision": False},
            {"id": "vision-model", "loaded": True, "vision": True},
        ]
        self.assertEqual(
            model_utils.resolve_model_name(
                "auto",
                "http://localhost:1234/v1",
                require_vision=True,
            ),
            "vision-model",
        )

    @patch("model_utils.discover_models")
    def test_auto_vision_requires_known_vision_capability(self, discover):
        discover.return_value = [
            {"id": "unknown-model", "loaded": True, "vision": False},
        ]
        with self.assertRaisesRegex(
            model_utils.ModelDiscoveryError,
            "no vision-capable model",
        ):
            model_utils.resolve_model_name(
                "auto",
                "http://localhost:1234/v1",
                require_vision=True,
            )


if __name__ == "__main__":
    unittest.main()
