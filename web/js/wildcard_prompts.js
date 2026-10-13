import { app } from "../../../scripts/app.js";

function resetSequence(node, recordChange = true) {
    const index = node.widgets?.find((widget) => widget.name === "sequence_index");
    if (!index) return;
    if (recordChange) node.graph?.beforeChange?.();
    index.value = 0;
    index.callback?.(index.value);
    if (recordChange) node.graph?.afterChange?.();
    node.graph?.setDirtyCanvas?.(true, true);
}

function frontendButton(node, name, callback) {
    const widget = node.addWidget("button", name, null, callback, { serialize: false });
    widget.serialize = false;
    widget.serializeValue = () => undefined;
    return widget;
}

app.registerExtension({
    name: "cyberdelia.wildcard.loadPrompts",
    nodeCreated(node) {
        if (node.comfyClass !== "WildcardLoRAPromptsV3") return;

        const index = node.widgets?.find((widget) => widget.name === "sequence_index");
        if (index) {
            const previousAfterQueued = index.afterQueued;
            index.afterQueued = function (...args) {
                const result = previousAfterQueued?.apply(this, args);
                const mode = node.widgets?.find((widget) => widget.name === "mode");
                const enabled = node.widgets?.find((widget) => widget.name === "enabled");
                // Connected indices are owned by the upstream node/API client.
                const connected = node.inputs?.some((input) => input.name === "sequence_index" && input.link != null);
                if (mode?.value === "sequential prompt" && enabled?.value !== false && !connected) {
                    // afterQueued runs after serialization and successful submission,
                    // once for each entry in Run's batch count, not after execution.
                    const value = Number(index.value);
                    if (Number.isSafeInteger(value) && value >= 0) {
                        index.value = Math.min(value + 1, 0xFFFFFFFF);
                        node.graph?.setDirtyCanvas?.(true, true);
                    }
                }
                return result;
            };
        }

        frontendButton(node, "Load .txt", () => {
            const picker = document.createElement("input");
            picker.type = "file";
            picker.accept = ".txt,text/plain";
            picker.addEventListener("change", async () => {
                const file = picker.files?.[0];
                if (!file) return;
                try {
                    const text = await file.text();
                    const prompts = node.widgets?.find((widget) => widget.name === "prompts");
                    const path = node.widgets?.find((widget) => widget.name === "prompt_file");
                    if (!prompts) throw new Error("The prompts field is unavailable.");
                    node.graph?.beforeChange?.();
                    prompts.value = text.replace(/^\uFEFF/, "");
                    prompts.callback?.(prompts.value);
                    // Loading a browser file switches back to the pasted-text source.
                    if (path) {
                        path.value = "";
                        path.callback?.(path.value);
                    }
                    resetSequence(node, false);
                    node.graph?.afterChange?.();
                    node.graph?.setDirtyCanvas?.(true, true);
                } catch (error) {
                    window.alert(`Could not load the prompt file: ${error.message}`);
                }
            }, { once: true });
            picker.click();
        });
        frontendButton(node, "Reset sequence", () => resetSequence(node));
    },
});
