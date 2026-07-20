import importlib.util
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock, patch

from _requests_stub import ensure_requests

requests = ensure_requests()


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

node_module = sys.modules[f"{PACKAGE_NAME}.z_engineer"]
CyberdeliaZEngineer = node_module.CyberdeliaZEngineer


class FakeClip:
    def tokenize(self, text):
        return f"tokens:{text}"

    def encode_from_tokens_scheduled(self, tokens):
        return f"conditioning:{tokens}"


def response_with(content):
    response = Mock()
    response.raise_for_status.return_value = None
    response.json.return_value = {"choices": [{"message": {"content": content}}]}
    return response


def http_error(status):
    response = Mock()
    response.status_code = status
    response.headers = {}
    return requests.exceptions.HTTPError(f"HTTP {status}", response=response)


class NodeTests(unittest.TestCase):
    def setUp(self):
        self.node = CyberdeliaZEngineer()
        self.clip = FakeClip()
        self.base_args = {
            "clip": self.clip,
            "mode": True,
            "text": "two robots",
            "system_prompt": "Return an image prompt.",
            "api_url": "http://localhost:1234/v1",
            "model": "manual-model",
            "seed": 0,
            "temperature": 0.7,
            "max_tokens": 600,
            "timeout": 120,
        }

    def test_existing_required_widget_order_is_preserved(self):
        required = list(CyberdeliaZEngineer.INPUT_TYPES()["required"])
        self.assertEqual(
            required,
            [
                "clip",
                "mode",
                "text",
                "system_prompt",
                "api_url",
                "model",
                "seed",
                "temperature",
                "max_tokens",
                "timeout",
            ],
        )
        self.assertIn("image", CyberdeliaZEngineer.INPUT_TYPES()["optional"])

    def test_retry_then_success(self):
        with (
            patch.object(
                node_module.requests,
                "post",
                side_effect=[
                    requests.exceptions.ConnectionError("temporary"),
                    response_with("Final prompt: A polished scene."),
                ],
            ) as post,
            patch.object(node_module.time, "sleep") as sleep,
        ):
            result = self.node.generate_prompt(**self.base_args, retries=1)

        self.assertEqual(result[2], "A polished scene.")
        self.assertEqual(post.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_http_500_is_retried(self):
        with (
            patch.object(
                node_module.requests,
                "post",
                side_effect=[http_error(500), response_with("A recovered prompt.")],
            ) as post,
            patch.object(node_module.time, "sleep"),
        ):
            result = self.node.generate_prompt(**self.base_args, retries=1)
        self.assertEqual(result[2], "A recovered prompt.")
        self.assertEqual(post.call_count, 2)

    def test_http_400_is_not_retried(self):
        with patch.object(
            node_module.requests,
            "post",
            side_effect=http_error(400),
        ) as post:
            result = self.node.generate_prompt(**self.base_args, retries=3)
        self.assertEqual(result[2], "two robots")
        self.assertEqual(post.call_count, 1)

    def test_fallback_input_error_mode(self):
        with patch.object(
            node_module.requests,
            "post",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            result = self.node.generate_prompt(
                **self.base_args,
                retries=0,
                error_mode="fallback_input",
            )
        self.assertEqual(result[2], "two robots")

    def test_empty_error_mode(self):
        with patch.object(
            node_module.requests,
            "post",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            result = self.node.generate_prompt(
                **self.base_args,
                retries=0,
                error_mode="empty",
            )
        self.assertEqual(result[2], "")

    def test_stop_error_mode(self):
        with patch.object(
            node_module.requests,
            "post",
            side_effect=requests.exceptions.ConnectionError("offline"),
        ):
            with self.assertRaises(requests.exceptions.ConnectionError):
                self.node.generate_prompt(
                    **self.base_args,
                    retries=0,
                    error_mode="stop",
                )

    def test_cleaning_keep_terms_and_constraints_pipeline(self):
        with patch.object(
            node_module.requests,
            "post",
            return_value=response_with(
                "<think>draft</think>\nFinal prompt: Robots in a studio.\n"
                "Negative prompt: blur"
            ),
        ):
            result = self.node.generate_prompt(
                **self.base_args,
                keep_terms="m4rty style",
                preserve_constraints=True,
            )
        self.assertEqual(result[2], "Robots in a studio, with two robots, m4rty style.")

    def test_image_builds_vision_request_and_allows_empty_text(self):
        with (
            patch.object(
                node_module,
                "resolve_model_name",
                return_value="vision-model",
            ) as resolve_model,
            patch.object(
                node_module,
                "image_to_data_url",
                return_value="data:image/jpeg;base64,example",
            ),
            patch.object(
                node_module.requests,
                "post",
                return_value=response_with("A detailed image prompt."),
            ) as post,
        ):
            args = dict(self.base_args)
            args.update(text="", model="auto")
            result = self.node.generate_prompt(**args, image=object())

        self.assertEqual(result[2], "A detailed image prompt.")
        resolve_model.assert_called_once_with(
            "auto",
            "http://localhost:1234/v1",
            timeout=120,
            require_vision=True,
        )
        content = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertEqual(content[0]["type"], "text")
        self.assertIn("Analyze the attached image", content[0]["text"])
        self.assertEqual(
            content[1],
            {
                "type": "image_url",
                "image_url": {
                    "url": "data:image/jpeg;base64,example",
                    "detail": "auto",
                },
            },
        )

    def test_image_request_includes_user_direction(self):
        with (
            patch.object(node_module, "image_to_data_url", return_value="data:image/png;base64,x"),
            patch.object(
                node_module.requests,
                "post",
                return_value=response_with("A focused image prompt."),
            ) as post,
        ):
            self.node.generate_prompt(
                **self.base_args,
                image=object(),
            )

        content = post.call_args.kwargs["json"]["messages"][1]["content"]
        self.assertIn("Additional direction from the user:\ntwo robots", content[0]["text"])

    def test_passthrough_ignores_connected_image(self):
        with (
            patch.object(node_module, "image_to_data_url") as encode_image,
            patch.object(node_module.requests, "post") as post,
        ):
            result = self.node.generate_prompt(
                **{**self.base_args, "mode": False},
                image=object(),
            )

        self.assertEqual(result[2], "two robots")
        encode_image.assert_not_called()
        post.assert_not_called()


if __name__ == "__main__":
    unittest.main()
