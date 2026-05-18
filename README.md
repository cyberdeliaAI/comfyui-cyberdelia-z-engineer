# comfyui-cyberdelia-z-engineer

LLM-powered prompt engineering node for **Z-Image Turbo** workflows in ComfyUI.

By **Cyberdelia AI Lab** · [github.com/cyberdeliaAI](https://github.com/cyberdeliaAI)

---

## What it does

Sends your input prompt to a local LLM via an OpenAI-compatible API (LM Studio, Ollama, etc.), receives an enhanced prompt back, and CLIP-encodes the result directly into a positive conditioning output ready for your sampler. Also outputs an empty negative conditioning for save-node compatibility.

The text widget is named `text` so that metadata extension and image saver nodes following the standard CLIPTextEncode capture pattern will automatically pick up the prompt for embedding in PNG metadata.

### Features

- **CLIP encoding built-in** — connects directly to your sampler, no separate CLIPTextEncode node needed
- **Dual conditioning outputs** — positive (engineered or passthrough) + empty negative
- **STRING output** for preview, metadata, or debugging
- **Mode toggle** — switch between `engineered (LLM)` and `passthrough (raw)` without rewiring
- **Graceful fallback** — if the LLM is unreachable, falls back to the raw input prompt so your workflow keeps rendering
- **Metadata extension friendly** — standard `text` widget name plays nicely with image savers

### Requirements

- A recent version of ComfyUI (one that exposes `clip.encode_from_tokens_scheduled`)
- A running OpenAI-compatible LLM endpoint, for example:
  - [LM Studio](https://lmstudio.ai/) — default URL `http://localhost:1234/v1`
  - Ollama with OpenAI compatibility enabled
  - Any other OpenAI-compatible server
- **Recommended model**: Qwen3-4B (or any 4B+ instruction-following model)

### Installation

**Via ComfyUI-Manager**: search for *Cyberdelia* and install.

**Manual install**:

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/cyberdeliaAI/comfyui-cyberdelia-z-engineer.git
```

Then restart ComfyUI.

### Usage

1. Add the **Cyberdelia Z-Engineer** node — it lives under `Cyberdelia/Prompt` in the node menu.
2. Connect `CLIP` (from your model / LoRA loader) to the node's `clip` input.
3. Connect the `positive` output to your KSampler's positive conditioning input.
4. Connect the `negative` output to the KSampler's negative input (it's empty but valid).
5. Type your concept in the `text` field.
6. Paste a Z-Image-tuned system prompt in `system_prompt` (see below).
7. Set `api_url` to your LLM server URL.
8. Set `model` to the exact model identifier as loaded in your server.
9. Toggle `mode` between **engineered** and **passthrough** as needed.

### Recommended system prompt for Z-Image Turbo

```
Interpret the user seed as production intent, then build a definitive 200-250 word single-paragraph image prompt that preserves every explicit constraint while intelligently expanding missing details. First infer the core subject, action, setting, and emotional tone; treat these as non-negotiable anchors. Then enhance with precise visual staging (explicit foreground, midground, background), clear visual hierarchy and eye path, physically plausible lighting (source, direction, softness, color temperature), and optical strategy (if lens/aperture are provided, preserve exactly; if absent, choose fitting lens and aperture and imply their depth-of-field effect). Integrate organic, manufactured, and environmental textures with realistic material behavior, add motion/atmospheric cues only when they support the scene, and apply a coherent color grade consistent with mood and environment. Keep the prose vivid but controlled: no contradictions, no overstuffing, no generic filler. Do not mention camera body brands. Output one polished paragraph only, no bullets, no line breaks, no meta commentary.
```

> Note: in the system prompt above, "user seed" refers to the user's input idea (the raw concept), not the numerical seed parameter of the node.

### Parameters

| Parameter | Description |
|-----------|-------------|
| `clip` | CLIP model from your model / LoRA loader |
| `mode` | `engineered (LLM)` → calls the LLM; `passthrough (raw)` → uses input text unchanged |
| `text` | Your concept / seed prompt (this is also what metadata savers will capture) |
| `system_prompt` | Instructions for the LLM (see recommended prompt above) |
| `api_url` | OpenAI-compatible base URL, e.g. `http://localhost:1234/v1` |
| `model` | Model identifier as loaded in your LLM server |
| `seed` | LLM sampling seed — combine with `control_after_generate` for variation per run |
| `temperature` | Sampling temperature (`0.0` = deterministic) |
| `max_tokens` | Output token cap (default `600`) |
| `timeout` | HTTP timeout in seconds (default `120`) |

### Outputs

| Output | Type | Description |
|--------|------|-------------|
| `positive` | `CONDITIONING` | CLIP-encoded engineered or raw prompt |
| `negative` | `CONDITIONING` | CLIP-encoded empty string — save-node compatible |
| `prompt` | `STRING` | The final text used for encoding (useful for preview / metadata) |

### Metadata capture

The `text` widget name matches the convention used by `CLIPTextEncode`, so common image saver / metadata extension nodes will automatically capture your input prompt and embed it in the saved PNG. Note that what gets saved is the **raw user input**, not the engineered LLM output — the latter is a runtime value and isn't part of the workflow JSON.

If you specifically want the engineered text in the metadata, route the `prompt` STRING output directly into your saver's prompt-text input.

### Tips

- **Reproducibility**: set `mode` to engineered, fix the seed (`control_after_generate: fixed`), and use a low temperature. Note that local LLMs are not 100% deterministic — KV cache state and quantization can introduce small variations.
- **Variation**: set `control_after_generate: randomize` to get a different engineered prompt each run for the same input.
- **Debugging**: hook the `prompt` STRING output into a ShowText node (e.g. from pysssss / WAS Node Suite) to see the engineered output before encoding.

### License

MIT — see [LICENSE](LICENSE).

### Credits

Built by **Cyberdelia AI Lab** · [github.com/cyberdeliaAI](https://github.com/cyberdeliaAI)
