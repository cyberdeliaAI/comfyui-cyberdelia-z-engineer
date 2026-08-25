import { app } from "../../../scripts/app.js";
import { api } from "../../../scripts/api.js";


const NODE_NAMES = new Set([
    "CyberdeliaZEngineer",
    "CyberdeliaPromptEngineerText",
]);
const CUSTOM_PRESET = "Custom";
const AUTO_MODEL = "Auto";
const MANUAL_MODEL = "[use model field]";
const REFRESH_PRESETS = "↻ Refresh presets";
const REFRESH_MODELS = "↻ Refresh models";


function getWidget(node, name) {
    return node.widgets?.find((widget) => widget.name === name) ?? null;
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


function findPresetMatch(node) {
    const prompt = String(getWidget(node, "system_prompt")?.value ?? "").trim();
    for (const [name, value] of node.__zEngineerPresets ?? []) {
        if (String(value).trim() === prompt) {
            return name;
        }
    }
    return CUSTOM_PRESET;
}


async function refreshPresets(node) {
    const selector = getWidget(node, "system_prompt_preset_selector");
    if (!selector) {
        return;
    }
    try {
        const response = await api.fetchApi("/cyberdelia/z-engineer/presets");
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || `HTTP ${response.status}`);
        }
        node.__zEngineerPresets = new Map(
            (payload.presets ?? []).map((preset) => [preset.name, preset.prompt])
        );
        const values = [CUSTOM_PRESET, ...node.__zEngineerPresets.keys(), REFRESH_PRESETS];
        setComboValues(selector, values);
        selector.value = findPresetMatch(node);
        node.setDirtyCanvas?.(true, true);
    } catch (error) {
        console.warn("[Prompt Engineer] Could not refresh presets", error);
        setComboValues(selector, [CUSTOM_PRESET, "[presets unavailable]", REFRESH_PRESETS]);
        selector.value = CUSTOM_PRESET;
    }
}


function ensurePresetSelector(node) {
    let selector = getWidget(node, "system_prompt_preset_selector");
    if (selector) {
        return selector;
    }

    selector = markFrontendOnly(node.addWidget(
        "combo",
        "system_prompt_preset_selector",
        CUSTOM_PRESET,
        async (value) => {
            if (value === REFRESH_PRESETS) {
                await refreshPresets(node);
                return;
            }
            if (value === CUSTOM_PRESET || !node.__zEngineerPresets?.has(value)) {
                return;
            }
            const systemPrompt = getWidget(node, "system_prompt");
            if (!systemPrompt) {
                return;
            }
            node.__zEngineerApplyingPreset = true;
            try {
                setWidgetValue(systemPrompt, node.__zEngineerPresets.get(value));
            } finally {
                node.__zEngineerApplyingPreset = false;
            }
            selector.value = value;
            node.setDirtyCanvas?.(true, true);
        },
        { values: [CUSTOM_PRESET, REFRESH_PRESETS] }
    ));

    const systemPrompt = getWidget(node, "system_prompt");
    if (systemPrompt && !systemPrompt.__zEngineerPresetTracking) {
        const previousCallback = systemPrompt.callback;
        systemPrompt.callback = function (...args) {
            const result = previousCallback?.apply(this, args);
            if (!node.__zEngineerApplyingPreset) {
                selector.value = CUSTOM_PRESET;
            }
            return result;
        };
        systemPrompt.inputEl?.addEventListener("input", () => {
            if (!node.__zEngineerApplyingPreset) {
                selector.value = CUSTOM_PRESET;
            }
        });
        systemPrompt.__zEngineerPresetTracking = true;
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


function setupNode(node) {
    node.__zEngineerUiReady = true;
    ensurePresetSelector(node);
    ensureModelSelector(node);
    refreshPresets(node);
    refreshModels(node);
}


app.registerExtension({
    name: "cyberdelia.z_engineer.controls",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (!NODE_NAMES.has(nodeData.name)) {
            return;
        }

        const previousOnNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const result = previousOnNodeCreated?.apply(this, arguments);
            setupNode(this);
            return result;
        };

        const previousConfigure = nodeType.prototype.configure;
        nodeType.prototype.configure = function () {
            const result = previousConfigure?.apply(this, arguments);
            setupNode(this);
            return result;
        };
    },
});
