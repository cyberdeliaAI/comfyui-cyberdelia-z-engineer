import { app } from "../../../scripts/app.js";

app.registerExtension({
    name: "cyberdelia.wildcard.loadPrompts",
    nodeCreated(node) {
        if (node.comfyClass !== "WildcardLoRAPromptsV3") return;

        node.addWidget("button", "Load .txt", null, () => {
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
                    node.graph?.afterChange?.();
                    node.graph?.setDirtyCanvas?.(true, true);
                } catch (error) {
                    window.alert(`Could not load the prompt file: ${error.message}`);
                }
            }, { once: true });
            picker.click();
        }, { serialize: false });
    },
});
