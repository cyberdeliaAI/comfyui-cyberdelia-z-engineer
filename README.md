# comfyui-cyberdelia-z-engineer

Model-independent, LLM-powered prompt engineering for ComfyUI. The node calls an OpenAI-compatible API, cleans and preserves the generated prompt, and CLIP-encodes it directly into sampler-ready conditioning.

By **Cyberdelia AI Lab** · [github.com/cyberdeliaAI](https://github.com/cyberdeliaAI)

---

![Cyberdelia Z-Engineer node in ComfyUI: raw concept input on the left, engineered image prompt output on the right](assets/sample.png)

## What it does

**Cyberdelia Z-Engineer** sends a seed prompt to LM Studio, Ollama, or another OpenAI-compatible server. It returns:

- positive conditioning encoded from the enhanced prompt;
- empty negative conditioning for save-node compatibility;
- the final enhanced prompt as a string.

Existing workflows can bypass the LLM with the built-in passthrough toggle.

## Features

- **CLIP encoding built in** — no separate CLIP Text Encode node required
- **Companion input node** — control the LLM/passthrough mode and prompt from one connectable node
- **Image-to-prompt vision input** — connect ComfyUI's Load Image output to describe an image with a vision model
- **Automatic LM Studio model discovery** — loaded LLMs are marked in a model selector
- **Safe `auto` model selection** — only chooses when one model is unambiguous
- **System-prompt presets** — one bundled Cyberdelia preset plus user-authored `.txt` presets
- **Visible preset content** — selecting a preset fills the normal, editable `system_prompt` field
- **Keep terms** — preserve LoRA triggers, names, or phrases verbatim
- **Optional constraint preservation** — conservatively retains quoted text, counts, colors, codes, and lens/aperture details
- **Output cleaning** — strips reasoning blocks, ChatML, Markdown fences, prompt labels, negative-prompt sections, and excess whitespace
- **Configurable error handling** — fall back to input, stop the workflow, or return empty conditioning
- **Targeted retries** — retries transient connection, timeout, HTTP 429, and HTTP 5xx failures
- **Metadata-friendly runtime output** — publishes the actually encoded text to compatible metadata extensions

## Requirements

- A recent ComfyUI version with `clip.encode_from_tokens_scheduled`
- A running OpenAI-compatible chat-completions endpoint
- `requests`

LM Studio is recommended because it also exposes loaded-model information through its native model API. Other OpenAI-compatible servers remain supported through the manual `model` field and `/v1/models` fallback.

Image-to-prompt additionally requires a vision-capable chat model. Pillow and PyTorch are already provided by ComfyUI.

## Installation

Via ComfyUI Manager, search for **Cyberdelia** and install the node.

Manual installation:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/cyberdeliaAI/comfyui-cyberdelia-z-engineer.git
pip install -r comfyui-cyberdelia-z-engineer/requirements.txt
```

Restart ComfyUI after installation or updating.

## Basic usage

1. Add **Cyberdelia Z-Engineer** from `Cyberdelia/Prompt`.
2. Connect the `CLIP` output from your model or LoRA loader.
3. Connect `positive` and `negative` to the sampler.
4. Enter a seed prompt in `text`.
5. Choose a system-prompt preset or keep `Custom` and edit `system_prompt` directly.
6. Set the OpenAI-compatible `api_url`.
7. Choose a discovered model, enter a manual model ID, or use `auto`.
8. Queue the workflow.

## Z-Engineer Input node

**Cyberdelia Z-Engineer Input** provides two reusable outputs:

| Output | Type | Connect to Z-Engineer |
| --- | --- | --- |
| `mode` | `BOOLEAN` | `mode` |
| `prompt` | `STRING` | `text` |

Set the toggle to **engineered (LLM)** or **passthrough (raw)** and enter the prompt in the multiline field. In the Z-Engineer node, convert the `mode` and `text` widgets to inputs using ComfyUI's **Convert Widget to Input** action, then connect both outputs. The original widgets and existing workflows remain unchanged when the companion node is not used.

## Model selection

The frontend model selector is a convenience control that updates the existing `model` field, so the selected model remains stored in the workflow.

`auto` follows conservative rules:

1. If exactly one LLM is loaded, use it.
2. If nothing is loaded and exactly one LLM is available, use it.
3. If multiple choices are possible, report an ambiguity instead of choosing arbitrarily.

Loaded models are shown first and marked `[loaded]`; models that report image-input support are marked `[vision]`. Embedding models are excluded. Use **↻ Refresh models** after changing models in LM Studio. If discovery is unavailable, type a model ID in the existing `model` field.

The node does not call LM Studio's model-management endpoints and never unloads or evicts models. A normal chat request can still trigger LM Studio's own JIT loading if that option is enabled in LM Studio.

## Image to prompt

The optional `image` input accepts the `IMAGE` output from ComfyUI's **Load Image** node:

1. Add **Load Image** and select an image.
2. Connect its `IMAGE` output to Z-Engineer's `image` input.
3. Enable `use_vision`.
4. Enter the image-specific instructions in `vision_system_prompt`.
5. Select a model marked `[vision]`, or use `auto`.
6. Enable **engineered (LLM)** and queue the workflow.

| Main `mode` | `use_vision` | Behavior |
| --- | --- | --- |
| passthrough | either | Return `text` unchanged; do not call the LLM |
| engineered | off | Use `system_prompt` for normal text-to-prompt enhancement |
| engineered | on | Require `image` and use `vision_system_prompt` for image-to-prompt |

With `use_vision` enabled, Z-Engineer requires an image and uses `vision_system_prompt` instead of the normal `system_prompt`. The `text` field is optional: leave it empty for a direct image-to-prompt conversion, or use it to request changes, for example `Make it a night scene in Tokyo`.

With `auto`, Z-Engineer considers only models that LM Studio explicitly reports as vision-capable. A manually entered model ID remains available for other OpenAI-compatible servers whose model list does not expose capability metadata.

With `use_vision` disabled, the normal `system_prompt` and text-to-prompt path are used, even if an image remains connected. The first image in a vision batch is resized to a maximum dimension of 1536 pixels, encoded locally, and sent as a base64 image content block. The image is also ignored in passthrough mode.

## Presets

The bundled preset is **Cyberdelia Detailed 200–250**. `Custom` remains the default and uses the visible `system_prompt` value unchanged.

The requested 200–250-word range is an instruction to the selected model; the node does not mechanically rewrite or pad the result to enforce that length.

To add a personal preset, create a UTF-8 `.txt` file in:

```text
ComfyUI/user/z_engineer/presets/
```

If ComfyUI was started with a custom user directory, the `z_engineer/presets` folder is created under that directory instead. The filename becomes the dropdown label and the complete file content becomes the system prompt.

Choose **↻ Refresh presets** after adding or editing a file. Selecting a preset copies its full text into `system_prompt`; editing that field switches the selector back to `Custom`. Because the actual text is stored in the workflow, old workflows stay reproducible if a preset file later changes.

Presets intentionally contain no model or sampling settings.

## Preservation and cleaning

`keep_terms` accepts terms separated by commas, semicolons, or line breaks:

```text
m4rty style, OHWX woman, neon_glow
```

The node asks the LLM to retain them and deterministically appends any missing terms with their original casing.

`preserve_constraints` is off by default. When enabled, it applies the same two-stage instruction and post-check to conservative constraints extracted from the seed:

- quoted text;
- counts up to twenty or numeric counts;
- color/object phrases;
- code-like identifiers such as `RX-78`;
- lens/aperture strings such as `24-70mm f/2.8`.

It does not add model-specific instructions, force a target word count, or pad short prompts.

`clean_output` is on by default. It removes technical model artefacts but does not remove camera brands or rewrite the prompt style.

## Error handling and retries

`error_mode` controls what happens after the request ultimately fails:

| Mode | Result |
| --- | --- |
| `fallback_input` | Continue with the original seed prompt (default) |
| `stop` | Raise the original error and stop the workflow |
| `empty` | Return empty positive and negative conditioning |

`retries` defaults to `1`, meaning one initial attempt plus one retry. Retries are limited to connection errors, timeouts, HTTP 429, and HTTP 5xx responses, with a short backoff. Permanent request errors are not retried.

Fallback and passthrough text are never cleaned or modified.

## Parameters

| Parameter | Description |
| --- | --- |
| `clip` | CLIP model used to encode the final prompt |
| `mode` | Enhanced LLM mode or raw passthrough |
| `text` | Input concept or seed prompt |
| `system_prompt` | Visible instructions sent to the LLM |
| `api_url` | OpenAI-compatible base URL, normally `http://localhost:1234/v1` |
| `model` | Manual model ID or `auto` |
| `seed` | Sampling seed sent to the API |
| `temperature` | Sampling temperature sent to the API |
| `max_tokens` | Maximum output tokens sent to the API |
| `timeout` | Request timeout in seconds |
| `keep_terms` | Exact terms that must survive generation |
| `preserve_constraints` | Enable conservative seed-constraint preservation |
| `clean_output` | Remove technical LLM output artefacts |
| `error_mode` | `fallback_input`, `stop`, or `empty` |
| `retries` | Number of transient-error retries, from 0 to 3 |
| `use_vision` | Switch between normal text enhancement and image-to-prompt |
| `vision_system_prompt` | Separate system instructions used only in vision mode |
| `image` | Optional ComfyUI image sent to a vision model for image-to-prompt generation |

`top_p`, `top_k`, and `min_p` are deliberately not sent; configure them in LM Studio or your chosen server.

## Outputs

| Output | Type | Description |
| --- | --- | --- |
| `positive` | `CONDITIONING` | CLIP-encoded final prompt |
| `negative` | `CONDITIONING` | CLIP-encoded empty string |
| `prompt` | `STRING` | Exact text used for positive conditioning |

For guaranteed metadata capture, connect `prompt` directly to the prompt-text input of your image saver. Compatible metadata extensions may also receive the resolved runtime text through the node's metadata cache integration.

## Testing

Run the standalone unit tests from the custom-node directory:

```bash
python -m unittest discover -s tests -v
```

## License

MIT — see [LICENSE](LICENSE).

## Credits

Built by **Cyberdelia AI Lab** · [github.com/cyberdeliaAI](https://github.com/cyberdeliaAI)

Based on [**ComfyUI-Z-Engineer**](https://github.com/BennyDaBall930/ComfyUI-Z-Engineer) by [BennyDaBall930](https://github.com/BennyDaBall930) (MIT licensed).
