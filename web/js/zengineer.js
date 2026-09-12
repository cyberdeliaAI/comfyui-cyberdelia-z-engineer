import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";


const PRESET_NODE_NAMES = new Set([
    "CyberdeliaZEngineer",
    "CyberdeliaPromptEngineerText",
]);
const MODEL_NODE_NAMES = new Set([
    ...PRESET_NODE_NAMES,
    "CyberdeliaDanbooruPrompt",
]);
const CUSTOM_PRESET = "Custom";
const AUTO_MODEL = "Auto";
const MANUAL_MODEL = "[use model field]";
const REFRESH_PRESETS = "↻ Refresh presets";
const REFRESH_VISION_PRESETS = "↻ Refresh vision presets";
const REFRESH_MODELS = "↻ Refresh models";
const DANBOORU_NODE = "CyberdeliaDanbooruPrompt";
const CONTROL_NODE = "CyberdeliaPromptPresetControls";
const VISION_IMAGE_LOADER = "CyberdeliaVisionImageLoader";
const REMOVED_DANBOORU_TEMPLATE_PRESETS = new Set([
    "custom",
    "tags_only",
    "illustrious",
    "pony",
    "animagine_xl",
    "nova_anime_xl",
]);
const DANBOORU_ERROR_MODES = new Set(["stop", "fallback_input", "empty"]);
const PROMPT_PRESET_CONFIGS = [
    {
        selectorName: "system_prompt_preset_selector",
        promptName: "system_prompt",
        presetsProperty: "__zEngineerPresets",
        applyingProperty: "__zEngineerApplyingPreset",
        trackingProperty: "__zEngineerPresetTracking",
        endpoint: "/cyberdelia/z-engineer/presets",
        refreshLabel: REFRESH_PRESETS,
        unavailableLabel: "[presets unavailable]",
        logName: "system",
    },
    {
        selectorName: "vision_prompt_preset_selector",
        promptName: "vision_system_prompt",
        presetsProperty: "__zEngineerVisionPresets",
        applyingProperty: "__zEngineerApplyingVisionPreset",
        trackingProperty: "__zEngineerVisionPresetTracking",
        endpoint: "/cyberdelia/z-engineer/vision-presets",
        refreshLabel: REFRESH_VISION_PRESETS,
        unavailableLabel: "[vision presets unavailable]",
        logName: "Vision",
    },
];


function getWidget(node, name) {
    return node.widgets?.find((widget) => widget.name === name) ?? null;
}


function normalizedInputImage(value) {
    return String(value ?? "").replace(/\s+\[input\]$/i, "").trim();
}


function applyInputImageList(node, images) {
    const imageWidget = getWidget(node, "image");
    if (!imageWidget) {
        return;
    }
    const values = Array.isArray(images) ? images : [];
    const current = normalizedInputImage(imageWidget.value);
    setComboValues(imageWidget, values);
    const nextValue = values.includes(current) ? current : (values[0] ?? "");
    const selectionChanged = nextValue !== current;
    setWidgetValue(imageWidget, nextValue);
    if (selectionChanged) {
        node.imgs = null;
        node.imageIndex = null;
    }
    node.setDirtyCanvas?.(true, true);
}


async function refreshInputImages(node) {
    try {
        const response = await api.fetchApi("/cyberdelia/z-engineer/input-images");
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        applyInputImageList(node, payload.images);
    } catch (error) {
        console.warn("[Vision Image Loader] Could not refresh images", error);
        window.alert(`Could not refresh ComfyUI input images: ${error.message}`);
    }
}


async function deleteSelectedInputImage(node) {
    const imageWidget = getWidget(node, "image");
    const filename = normalizedInputImage(imageWidget?.value);
    if (!filename) {
        window.alert("Select an input image to delete.");
        return;
    }
    const confirmed = window.confirm(
        `Permanently delete "${filename}" from the ComfyUI input folder?`
    );
    if (!confirmed) {
        return;
    }
    try {
        const response = await api.fetchApi(
            "/cyberdelia/z-engineer/input-images/delete",
            {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ filename }),
            }
        );
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        applyInputImageList(node, payload.images);
    } catch (error) {
        console.warn("[Vision Image Loader] Could not delete image", error);
        window.alert(`Could not delete "${filename}": ${error.message}`);
    }
}


function setupVisionImageLoader(node) {
    if (node.__zEngineerImageLoaderReady) {
        return;
    }
    node.__zEngineerImageLoaderReady = true;
    markFrontendOnly(node.addWidget(
        "button",
        "↻ Refresh images",
        null,
        () => refreshInputImages(node)
    ));
    markFrontendOnly(node.addWidget(
        "button",
        "🗑 Delete selected image",
        null,
        () => deleteSelectedInputImage(node)
    ));
}


function migrateRemovedDanbooruTemplatePreset(info) {
    const values = info?.widgets_values;
    if (!Array.isArray(values)) {
        return info;
    }

    // The removed preset was one of the final optional widgets. Delete its
    // serialized value so error_mode and retries remain aligned in old workflows.
    const presetIndex = values.findIndex((value, index) => (
        index >= 10
        && REMOVED_DANBOORU_TEMPLATE_PRESETS.has(value)
        && DANBOORU_ERROR_MODES.has(values[index + 1])
        && Number.isInteger(values[index + 2])
    ));
    if (presetIndex < 0) {
        return info;
    }

    const migratedValues = [...values];
    migratedValues.splice(presetIndex, 1);
    return { ...info, widgets_values: migratedValues };
}


function markFrontendOnly(widget) {
    widget.serialize = false;
    widget.options ??= {};
    widget.options.serialize = false;
    widget.serializeValue = () => undefined;
    return widget;
}


function setWidgetValue(widget, value) {
    if (!widget || widget.value === value) {
        return;
    }
    widget.value = value;
    widget.callback?.(value);
}


function setComboValues(widget, values) {
    widget.options ??= {};
    widget.options.values = values;
}


function findPresetMatch(node, config) {
    const prompt = String(getWidget(node, config.promptName)?.value ?? "").trim();
    for (const [name, value] of node[config.presetsProperty] ?? []) {
        if (String(value).trim() === prompt) {
            return name;
        }
    }
    return CUSTOM_PRESET;
}


function syncPresetSelector(node, selector, config) {
    if (!selector || node[config.applyingProperty]) {
        return;
    }
    const matchingPreset = findPresetMatch(node, config);
    if (selector.value !== matchingPreset) {
        selector.value = matchingPreset;
        node.setDirtyCanvas?.(true, false);
    }
}


async function refreshPresets(node, config) {
    const selector = getWidget(node, config.selectorName);
    if (!selector) {
        return;
    }
    try {
        const response = await api.fetchApi(config.endpoint);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        node[config.presetsProperty] = new Map(
            (payload.presets ?? []).map((preset) => [preset.name, preset.prompt])
        );
        const values = [
            CUSTOM_PRESET,
            ...node[config.presetsProperty].keys(),
            config.refreshLabel,
        ];
        setComboValues(selector, values);
        syncPresetSelector(node, selector, config);
        node.setDirtyCanvas?.(true, true);
    } catch (error) {
        console.warn(`[Prompt Engineer] Could not refresh ${config.logName} presets`, error);
        setComboValues(selector, [
            CUSTOM_PRESET,
            config.unavailableLabel,
            config.refreshLabel,
        ]);
        selector.value = CUSTOM_PRESET;
    }
}


function ensurePresetSelector(node, config) {
    let selector = getWidget(node, config.selectorName);
    if (selector) {
        return selector;
    }

    selector = markFrontendOnly(node.addWidget(
        "combo",
        config.selectorName,
        CUSTOM_PRESET,
        async (value) => {
            if (value === config.refreshLabel) {
                await refreshPresets(node, config);
                return;
            }
            const presets = node[config.presetsProperty];
            if (value === CUSTOM_PRESET || !presets?.has(value)) {
                return;
            }
            const promptWidget = getWidget(node, config.promptName);
            if (!promptWidget) {
                return;
            }
            node[config.applyingProperty] = true;
            try {
                setWidgetValue(promptWidget, presets.get(value));
            } finally {
                node[config.applyingProperty] = false;
            }
            syncPresetSelector(node, selector, config);
            node.setDirtyCanvas?.(true, true);
        },
        { values: [CUSTOM_PRESET, config.refreshLabel] }
    ));

    const promptWidget = getWidget(node, config.promptName);
    if (promptWidget && !promptWidget[config.trackingProperty]) {
        const previousCallback = promptWidget.callback;
        promptWidget.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            syncPresetSelector(node, selector, config);
            return result;
        };
        promptWidget.inputEl?.addEventListener("input", () => {
            // Let ComfyUI update the widget value before comparing it with the
            // preset. Programmatic callbacks during execution are not edits.
            requestAnimationFrame(() => syncPresetSelector(node, selector, config));
        });
        promptWidget[config.trackingProperty] = true;
    }
    return selector;
}


function activeControlPresetConfig(node) {
    return getWidget(node, "use_vision")?.value
        ? PROMPT_PRESET_CONFIGS[1]
        : PROMPT_PRESET_CONFIGS[0];
}


function syncControlPresetSelector(node) {
    const selector = node.__zEngineerControlPresetSelector;
    if (!selector || node.__zEngineerApplyingControlPreset) {
        return;
    }
    const config = activeControlPresetConfig(node);
    const prompt = String(getWidget(node, "active_system_prompt")?.value ?? "").trim();
    let matchingPreset = CUSTOM_PRESET;
    for (const [name, value] of node[config.presetsProperty] ?? []) {
        if (String(value).trim() === prompt) {
            matchingPreset = name;
            break;
        }
    }
    selector.name = config.selectorName;
    if (selector.value !== matchingPreset) {
        selector.value = matchingPreset;
        node.setDirtyCanvas?.(true, false);
    }
}


async function refreshControlPresets(node) {
    const selector = node.__zEngineerControlPresetSelector;
    if (!selector) {
        return;
    }
    const config = activeControlPresetConfig(node);
    selector.name = config.selectorName;
    try {
        const response = await api.fetchApi(config.endpoint);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        // Ignore a stale response when Vision was toggled while loading.
        if (activeControlPresetConfig(node) !== config) {
            return;
        }
        node[config.presetsProperty] = new Map(
            (payload.presets ?? []).map((preset) => [preset.name, preset.prompt])
        );
        setComboValues(selector, [
            CUSTOM_PRESET,
            ...node[config.presetsProperty].keys(),
            config.refreshLabel,
        ]);
        syncControlPresetSelector(node);
        node.setDirtyCanvas?.(true, true);
    } catch (error) {
        if (activeControlPresetConfig(node) !== config) {
            return;
        }
        console.warn(`[Prompt Controls] Could not refresh ${config.logName} presets`, error);
        setComboValues(selector, [
            CUSTOM_PRESET,
            config.unavailableLabel,
            config.refreshLabel,
        ]);
        selector.value = CUSTOM_PRESET;
    }
}


function ensureControlPresetSelector(node) {
    if (node.__zEngineerControlPresetSelector) {
        return node.__zEngineerControlPresetSelector;
    }

    const initialConfig = activeControlPresetConfig(node);
    const selector = markFrontendOnly(node.addWidget(
        "combo",
        initialConfig.selectorName,
        CUSTOM_PRESET,
        async (value) => {
            const config = activeControlPresetConfig(node);
            if (value === config.refreshLabel) {
                await refreshControlPresets(node);
                return;
            }
            const presets = node[config.presetsProperty];
            if (value === CUSTOM_PRESET || !presets?.has(value)) {
                return;
            }
            const promptWidget = getWidget(node, "active_system_prompt");
            if (!promptWidget) {
                return;
            }
            node.__zEngineerApplyingControlPreset = true;
            try {
                setWidgetValue(promptWidget, presets.get(value));
            } finally {
                node.__zEngineerApplyingControlPreset = false;
            }
            syncControlPresetSelector(node);
            node.setDirtyCanvas?.(true, true);
        },
        { values: [CUSTOM_PRESET, initialConfig.refreshLabel] }
    ));
    node.__zEngineerControlPresetSelector = selector;

    const promptWidget = getWidget(node, "active_system_prompt");
    if (promptWidget && !promptWidget.__zEngineerControlPresetTracking) {
        const previousCallback = promptWidget.callback;
        promptWidget.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            syncControlPresetSelector(node);
            return result;
        };
        promptWidget.inputEl?.addEventListener("input", () => {
            requestAnimationFrame(() => syncControlPresetSelector(node));
        });
        promptWidget.__zEngineerControlPresetTracking = true;
    }

    const useVisionWidget = getWidget(node, "use_vision");
    if (useVisionWidget && !useVisionWidget.__zEngineerControlPresetTracking) {
        const previousCallback = useVisionWidget.callback;
        useVisionWidget.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            refreshControlPresets(node);
            return result;
        };
        useVisionWidget.__zEngineerControlPresetTracking = true;
    }
    return selector;
}


function modelSelectorValue(node) {
    const model = String(getWidget(node, "model")?.value ?? "").trim();
    if (!model || model.toLowerCase() === "auto") {
        return AUTO_MODEL;
    }
    for (const [label, value] of node.__zEngineerModels ?? []) {
        if (value === model) {
            return label;
        }
    }
    return MANUAL_MODEL;
}


async function refreshModels(node, force = false) {
    const selector = getWidget(node, "lmstudio_model_selector");
    const apiUrl = String(getWidget(node, "api_url")?.value ?? "").trim();
    if (!selector || !apiUrl) {
        return;
    }

    try {
        const query = new URLSearchParams({ api_url: apiUrl, force: force ? "1" : "0" });
        const response = await api.fetchApi(`/cyberdelia/z-engineer/models?${query}`);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        const entries = (payload.models ?? []).map((model) => {
            const markers = [
                model.loaded ? "[loaded]" : "",
                model.vision ? "[vision]" : "",
            ].filter(Boolean).join(" ");
            const label = markers ? `${model.id} ${markers}` : model.id;
            return [label, model.id];
        });
        node.__zEngineerModels = new Map(entries);
        setComboValues(selector, [
            AUTO_MODEL,
            MANUAL_MODEL,
            ...node.__zEngineerModels.keys(),
            REFRESH_MODELS,
        ]);
        selector.value = modelSelectorValue(node);
        node.setDirtyCanvas?.(true, true);
    } catch (error) {
        console.warn("[Prompt Engineer] Could not refresh models", error);
        node.__zEngineerModels = new Map();
        setComboValues(selector, [
            AUTO_MODEL,
            MANUAL_MODEL,
            "[model list unavailable]",
            REFRESH_MODELS,
        ]);
        selector.value = modelSelectorValue(node);
    }
}


function ensureModelSelector(node) {
    let selector = getWidget(node, "lmstudio_model_selector");
    if (selector) {
        return selector;
    }

    selector = markFrontendOnly(node.addWidget(
        "combo",
        "lmstudio_model_selector",
        AUTO_MODEL,
        async (value) => {
            if (value === REFRESH_MODELS) {
                await refreshModels(node, true);
                return;
            }
            const modelWidget = getWidget(node, "model");
            if (value === AUTO_MODEL) {
                setWidgetValue(modelWidget, "auto");
            } else if (value !== MANUAL_MODEL && node.__zEngineerModels?.has(value)) {
                setWidgetValue(modelWidget, node.__zEngineerModels.get(value));
            }
            selector.value = modelSelectorValue(node);
            node.setDirtyCanvas?.(true, true);
        },
        { values: [AUTO_MODEL, MANUAL_MODEL, REFRESH_MODELS] }
    ));

    const modelWidget = getWidget(node, "model");
    if (modelWidget && !modelWidget.__zEngineerModelTracking) {
        const previousCallback = modelWidget.callback;
        modelWidget.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            selector.value = modelSelectorValue(node);
            return result;
        };
        modelWidget.inputEl?.addEventListener("input", () => {
            selector.value = modelSelectorValue(node);
        });
        modelWidget.__zEngineerModelTracking = true;
    }

    const apiUrlWidget = getWidget(node, "api_url");
    if (apiUrlWidget && !apiUrlWidget.__zEngineerModelTracking) {
        const previousCallback = apiUrlWidget.callback;
        let refreshTimer = null;
        apiUrlWidget.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            window.clearTimeout(refreshTimer);
            refreshTimer = window.setTimeout(() => refreshModels(node, true), 350);
            return result;
        };
        apiUrlWidget.__zEngineerModelTracking = true;
    }
    return selector;
}


function setupNode(node, nodeName) {
    node.__zEngineerUiReady = true;
    if (nodeName === CONTROL_NODE) {
        ensureControlPresetSelector(node);
        refreshControlPresets(node);
        return;
    }
    if (PRESET_NODE_NAMES.has(nodeName)) {
        for (const config of PROMPT_PRESET_CONFIGS) {
            ensurePresetSelector(node, config);
            refreshPresets(node, config);
        }
    }
    ensureModelSelector(node);
    refreshModels(node);
}


app.registerExtension({
    name: "cyberdelia.z_engineer.controls",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (
            !MODEL_NODE_NAMES.has(nodeData.name)
            && nodeData.name !== CONTROL_NODE
            && nodeData.name !== VISION_IMAGE_LOADER
        ) {
            return;
        }

        const previousOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = previousOnNodeCreated?.apply(this, arguments);
            if (nodeData.name === VISION_IMAGE_LOADER) {
                setupVisionImageLoader(this);
                return result;
            }
            setupNode(this, nodeData.name);
            return result;
        };

        const previousConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function (info, ...rest) {
            const resolvedInfo = nodeData.name === DANBOORU_NODE
                ? migrateRemovedDanbooruTemplatePreset(info)
                : info;
            const result = previousConfigure?.call(this, resolvedInfo, ...rest);
            if (nodeData.name === VISION_IMAGE_LOADER) {
                setupVisionImageLoader(this);
                return result;
            }
            setupNode(this, nodeData.name);
            return result;
        };
    },
});
