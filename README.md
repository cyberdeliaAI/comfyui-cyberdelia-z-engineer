# Cyberdelia Prompt Engineer

Model-independent text, vision, and Danbooru prompt engineering for ComfyUI. Generate a reusable prompt string, validated anime tags, or CLIP-encoded sampler-ready conditioning.

The package and repository retain the legacy name `comfyui-cyberdelia-z-engineer` so existing installations and update paths remain compatible.

By **Cyberdelia AI Lab** · [github.com/cyberdeliaAI](https://github.com/cyberdeliaAI)

---

![Cyberdelia Prompt Engineer in ComfyUI: raw concept input on the left, engineered image prompt output on the right](assets/sample.png)

## What it does

Cyberdelia Prompt Engineer sends text, or an optional image plus instructions, to LM Studio, Ollama, or another OpenAI-compatible server. Two node variants share the same generation pipeline:

| Node | CLIP required | Outputs | Best for |
| --- | --- | --- | --- |
| **Prompt Engineer — Text** | No | Prompt `STRING` | Krea2, Flux, external encoders, metadata, image-to-prompt |
| **Prompt Engineer — Conditioning** | Yes | Positive, negative, prompt | Workflows that use normal CLIP conditioning directly |
| **Danbooru Prompt** | No | Prompt, tags, dropped tags | Anime checkpoints trained on booru-style captions |

Existing workflows can bypass the LLM with the built-in passthrough toggle.

The separate **Cyberdelia Danbooru Prompt** node converts a normal scene description into real Danbooru tags, validates them against a bundled local vocabulary, and optionally wraps them in a model-family template.

## Features

- **Prompt-only Text node** — text and Vision generation without loading or connecting CLIP
- **Optional direct CLIP encoding** — use the Conditioning variant when sampler-ready conditioning is wanted
- **Companion Controls node** — externally control LLM/passthrough, prompt, and Vision mode
- **Image-to-prompt vision input** — connect ComfyUI's Load Image output to describe an image with a vision model
- **Automatic LM Studio model discovery** — loaded LLMs are marked in a model selector
- **Safe `auto` model selection** — only chooses when one model is unambiguous
- **System-prompt presets** — one bundled Cyberdelia preset plus user-authored `.txt` presets
- **Visible preset content** — selecting a preset fills the normal, editable `system_prompt` field
- **Keep terms** — preserve LoRA triggers, names, or phrases verbatim
- **Optional constraint preservation** — conservatively retains quoted text, counts, colors, codes, and lens/aperture details
- **Output cleaning** — strips reasoning blocks, ChatML, Markdown fences, prompt labels, negative-prompt sections, and excess whitespace
- **Configurable error handling** — fall back to input, stop the workflow, or return an empty result
- **Targeted retries** — retries transient connection, timeout, HTTP 429, and HTTP 5xx failures
- **Metadata-friendly runtime output** — publishes the actually encoded text to compatible metadata extensions
- **Danbooru Prompt node** — converts natural language into validated booru-style tags
- **140k-tag local vocabulary** — resolves canonical tags, aliases, common word forms, and recoverable sub-phrases
- **Spaces or underscores** — output `blue eyes, long hair` or `blue_eyes, long_hair`
- **Danbooru ordering and filtering** — sort categories, exclude categories, filter rare tags, and inspect dropped candidates
- **Anime-model templates** — tags-only, Illustrious, Pony, Animagine XL, and Nova Anime XL

## Requirements

- A recent ComfyUI version
- A running OpenAI-compatible chat-completions endpoint
- `requests`

The Conditioning variant additionally requires a CLIP input with `clip.encode_from_tokens_scheduled`.

LM Studio is recommended because it also exposes loaded-model information through its native model API. Other OpenAI-compatible servers remain supported through the manual `model` field and `/v1/models` fallback.

Image-to-prompt additionally requires a vision-capable chat model. Pillow and PyTorch are already provided by ComfyUI.

Danbooru Prompt is most useful with anime checkpoints trained on booru tags. Its bundled vocabulary contains Danbooru terminology, including NSFW tags, and is a static snapshot rather than a live connection to Danbooru.

## Installation

Via ComfyUI Manager, search for **Cyberdelia** and install the node.

Manual installation:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/cyberdeliaAI/comfyui-cyberdelia-z-engineer.git
pip install -r comfyui-cyberdelia-z-engineer/requirements.txt
```

Restart ComfyUI after installation or updating.

## Danbooru Prompt node

1. Add **Cyberdelia Danbooru Prompt** from `Cyberdelia/Prompt`.
2. Describe the desired scene in normal language.
3. Select the local LLM and choose `spaces` or `underscores` for tag output.
4. Keep validation enabled to remove candidates that are not in the bundled Danbooru vocabulary.
5. Connect `prompt` to the checkpoint's text encoder. Use `tags` for custom wrapping or metadata, and `dropped_tags` to inspect filtered candidates.

The node uses the same API URL normalization, automatic model discovery, retries, and visible error handling as Prompt Engineer. Fuzzy matching is disabled by default because approximate matches can change meaning; values of `0.85` or higher are the safest starting point when it is needed.

### Danbooru outputs

| Output | Description |
| --- | --- |
| `prompt` | Validated tags wrapped in the custom or selected model template |
| `tags` | Validated tags only, rendered with spaces or underscores |
| `dropped_tags` | LLM candidates removed or only partially recovered by validation |

`tag_format=spaces` produces `1girl, blue eyes, long hair`. `tag_format=underscores` produces `1girl, blue_eyes, long_hair`. Template text is left unchanged, so fixed model syntax such as Pony's `score_9` remains intact.

Strict validation can recover a known sub-tag while removing an unknown modifier from a compound phrase. Such partial recovery is reported in `dropped_tags`; disable strict validation when retaining every LLM candidate intact is more important than vocabulary precision.

## Text node — no CLIP

1. Add **Cyberdelia Prompt Engineer — Text** from `Cyberdelia/Prompt`.
2. Enter a seed prompt, or connect **Load Image** and enable Vision.
3. Choose a system-prompt preset or edit the visible prompt instructions.
4. Set the API URL and select a model.
5. Connect `prompt` to Krea2, another text encoder, a preview node, or an image saver.

For a Krea2 workflow, the intended separation is:

```text
Load Image (optional) → Prompt Engineer — Text → Krea2 encoder → Krea2 conditioning
```

Krea2's model-specific hidden-state conditioning remains the responsibility of its encoder; Prompt Engineer supplies the reusable text.

## Conditioning node

1. Add **Cyberdelia Prompt Engineer — Conditioning**.
2. Connect the `CLIP` output from the model or LoRA loader.
3. Connect `positive` and `negative` to the sampler.
4. Configure text/Vision, prompt instructions, API, and model as above.

The internal ID remains `CyberdeliaZEngineer`, so workflows created with older versions continue to load with the same inputs and output indices.

## Prompt Controls node

**Cyberdelia Prompt Controls** provides three reusable outputs. The third output was appended so the legacy `mode` and `prompt` output indices remain unchanged.

| Output | Type | Connect to Prompt Engineer |
| --- | --- | --- |
| `mode` | `BOOLEAN` | `mode` |
| `prompt` | `STRING` | `text` |
| `use_vision` | `BOOLEAN` | `use_vision` |

Convert the corresponding widgets to inputs using ComfyUI's **Convert Widget to Input** action, then connect the desired controls.

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
2. Connect its `IMAGE` output to Prompt Engineer's `image` input.
3. Enable `use_vision`.
4. Enter the image-specific instructions in `vision_system_prompt`.
5. Select a model marked `[vision]`, or use `auto`.
6. Enable **engineered (LLM)** and queue the workflow.

| Main `mode` | `use_vision` | Behavior |
| --- | --- | --- |
| passthrough | either | Return `text` unchanged; do not call the LLM |
| engineered | off | Use `system_prompt` for normal text-to-prompt enhancement |
| engineered | on | Require `image` and use `vision_system_prompt` for image-to-prompt |

With `use_vision` enabled, Prompt Engineer requires an image and uses `vision_system_prompt` instead of the normal `system_prompt`. The `text` field is optional: leave it empty for a direct image-to-prompt conversion, or use it to request changes, for example `Make it a night scene in Tokyo`.

With `auto`, Prompt Engineer considers only models that LM Studio explicitly reports as vision-capable. A manually entered model ID remains available for other OpenAI-compatible servers whose model list does not expose capability metadata.

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
| `stop` | Show a clear error on the node and stop the workflow (default) |
| `fallback_input` | Continue with the original seed prompt |
| `empty` | Return an empty prompt; the Conditioning node also encodes empty conditioning |

`retries` defaults to `1`, meaning one initial attempt plus one retry. Retries are limited to connection errors, timeouts, HTTP 429, and HTTP 5xx responses, with a short backoff. Permanent request errors are not retried.

The LLM connection is only used and checked in engineered mode. Passthrough
returns the input directly without model discovery or any network request.
Fallback and passthrough text are never cleaned or modified.

## Parameters

| Parameter | Description |
| --- | --- |
| `clip` | CLIP model used only by the Conditioning node |
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

**Prompt Engineer — Text**

| Output | Type | Description |
| --- | --- | --- |
| `prompt` | `STRING` | Final generated, cleaned, or passthrough prompt |

**Prompt Engineer — Conditioning**

| Output | Type | Description |
| --- | --- | --- |
| `positive` | `CONDITIONING` | CLIP-encoded final prompt |
| `negative` | `CONDITIONING` | CLIP-encoded empty string |
| `prompt` | `STRING` | Exact text used for positive conditioning |

For guaranteed metadata capture, connect `prompt` directly to the prompt-text input of your image saver. Compatible metadata extensions may also receive the Conditioning node's resolved runtime text through its metadata cache integration.

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

Danbooru validation is adapted from [**ComfyUI-NeuralBooru**](https://github.com/ChrisJohnson89/ComfyUI-NeuralBooru). The bundled tag data is derived from [**a1111-sd-webui-tagcomplete**](https://github.com/DominikDoom/a1111-sd-webui-tagcomplete). See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
