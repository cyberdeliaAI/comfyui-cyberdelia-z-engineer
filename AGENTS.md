# Project Instructions

## Purpose and Architecture

Cyberdelia Prompt Engineer is a ComfyUI custom-node package for text and
Vision prompts, CLIP conditioning, prompt chains, wildcard templates, and
local Danbooru tag validation.

- `__init__.py`: node IDs, display names, `WEB_DIRECTORY`, and optional
  frontend route registration.
- `z_engineer.py`: shared generation pipeline, LLM requests, retries,
  error handling, Conditioning node, and optional metadata integration.
- `prompt_engineer_text.py`: the same pipeline without CLIP.
- `prompt_chain.py`: up to five sequential text transformations.
- `z_engineer_input.py` and `prompt_preset_controls.py`: companion Controls.
- `wildcard_prompts.py`: template expansion, search/replace, prefixes,
  seeded selection, and list outputs.
- `danbooru_node.py` and `danbooru_tags.py`: tag generation, validation,
  formatting, and prompt templates; vocabulary from `data/danbooru.csv`.
- `model_utils.py`: URL normalization, endpoint allowlisting,
  authentication, and model discovery.
- `prompt_utils.py`: output cleaning and term/constraint preservation.
- `vision_utils.py` and `image_loader.py`: image conversion and loading.
- `preset_manager.py`: bundled and personal text/Vision presets.
- `server_routes.py` and `web/js/`: ComfyUI frontend helpers.

## Workflow and Code Conventions

- Communicate in Dutch; use customary English technical terms.
- Read relevant source code and tests before making changes.
- Follow the existing structure, style, and naming conventions. Preserve
  English identifiers, comments, and documentation; do not translate them
  solely to change the language.
- Do not remove or substantially change existing functionality without
  explicit user permission.
- Distinguish verified behavior, assumptions, and potential bugs. Ask for
  clarification when missing information materially affects the work.

## Dependencies and Integrations

- Python backend; JavaScript ES modules without a separate build step.
- `requests` is the only explicitly declared Python dependency.
- ComfyUI supplies components including `folder_paths`, `PromptServer`,
  CLIP, PyTorch, NumPy, Pillow, and aiohttp.
- LLM generation uses OpenAI-compatible `/v1/chat/completions`.
  Discovery tries LM Studio `/api/v1/models`, then `/v1/models`.
- Package version and Comfy Registry identity are in `pyproject.toml`.

## Compatibility and Existing Design Choices

- Preserve existing node IDs, input/widget order, and output indices.
  Compatibility tests and frontend migrations protect older workflows.
- Legacy IDs include `CyberdeliaZEngineer`, `CyberdeliaZEngineerInput`,
  and `WildcardLoRAPromptsV3`.
- Text and Conditioning share `_generate_final_text()`. Conditioning
  encodes the final text as positive and an empty string as negative.
- Passthrough returns the original text unchanged without an LLM request
  in the generation pipeline.
- Preset selection copies instructions into ordinary workflow fields.
  Presets contain no model or sampling settings.
- `auto` selects a model only when the choice is unambiguous.
- Vision sends only the first batch image, with a maximum dimension of
  1536 pixels.
- Retries target connection errors, timeouts, HTTP 429, and HTTP 5xx.
- Danbooru uses a local database, not a live Danbooru API.
- Wildcard selection uses a local RNG; `prompts` is a list output.
- Sequential wildcard mode uses an explicit zero-based `sequence_index`,
  advanced by the frontend after each successful queue submission. API clients
  advance it themselves. `repeat_list` defaults off; exhausted sequences emit
  a silent ComfyUI `ExecutionBlocker`, never an empty generation prompt.
  Preserve legacy `random prompt` and `all prompts` modes and widget order.
- The wildcard `FUNCTION` is `run()`, which wraps `expand()` and adds a
  `wildcard_sequence` UI status in sequential mode (label, console warning and
  one notice when the list is finished). `expand()` keeps returning the tuple.
- The frontend advances the value ComfyUI actually receives: promoted subgraph
  inputs resolve to the host widget (one advance per host instance), repeated
  callbacks for shared subgraph definitions advance once per submission, and
  partial runs advance only the host instances that feed a selected node.
  Shared source widgets advance once per submission across wildcard nodes;
  active Primitive value controls retain ownership of their counters.
- Choice groups resolve innermost first; cleanup of spacing and commas runs
  only after a removal, so prompts without removals keep their formatting.
- Danbooru sub-phrase recovery skips stop words, artist tags and aliases that
  expand a fragment, and never uses fuzzy matching; complete candidates keep
  the existing validation, including fuzzy matching.
- Wildcard `prompt_file` paths are untrusted like API URLs: they must resolve
  inside ComfyUI's input folder or a folder in
  `CYBERDELIA_Z_ENGINEER_PROMPT_DIRS`, and files are limited to 10 MB.
- `fallback_prompt` is a lazy input, requested only while wildcards are off.
- Publishing to the Comfy Registry runs both Python and frontend test suites
  in the publish job before uploading; a failed suite prevents the upload.
- Preserve endpoint allowlisting and rejection of HTTP redirects.
  `CYBERDELIA_Z_ENGINEER_ALLOWED_API_URLS` takes precedence over the
  `OPENAI_API_BASE` fallback; explicit workflow URLs remain subject to the policy.
- API keys come from `CYBERDELIA_Z_ENGINEER_API_KEY`, falling back to
  `OPENAI_API_KEY`, not node widgets.
- Metadata integration is optional, not a hard dependency.

## Tests and Contributions

- Add or update relevant tests for behavior changes.
- Run from the repository root:
  `python -m unittest discover -s tests -v`
- GitHub Actions runs this suite with Python 3.11.
- Wildcard queue/frontend regression tests use Node.js 22 in GitHub Actions:
  `node --test tests/test_wildcard_frontend.mjs` (Node built-ins only).
- Tests use mocks and, when needed, a `requests` stub. They do not prove
  complete operation with ComfyUI, real models, or the frontend.
- Do not include models, checkpoints, credentials, or private workflow
  data in contributions.
- Consult `CONTRIBUTING.md`, `SECURITY.md`, and `THIRD_PARTY_NOTICES.md`
  when relevant.
