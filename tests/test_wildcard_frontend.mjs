import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../web/js/wildcard_prompts.js", import.meta.url), "utf8")
    .replace('import { app } from "../../../scripts/app.js";', "");

function createNode({ mode = "sequential prompt", enabled = true, index = 0, connected = false } = {}) {
    let extension;
    let fileChange;
    const picker = {
        files: [{ text: async () => "\uFEFFFirst\nSecond" }],
        addEventListener: (event, callback) => { fileChange = callback; },
        click() {},
    };
    vm.runInNewContext(source, {
        app: { registerExtension: (value) => { extension = value; } },
        document: { createElement: () => picker },
        window: { alert: (message) => { throw new Error(message); } },
    });
    const widgets = [
        { name: "prompts", value: "First\nSecond" },
        { name: "extra_tags", value: "" },
        { name: "prompt_file", value: "old.txt" },
        { name: "prompt_separator", value: "one per line" },
        { name: "search_replace", value: "" },
        { name: "replace_match", value: "whole words" },
        { name: "case_sensitive", value: false },
        { name: "prefix", value: "" },
        { name: "mode", value: mode },
        { name: "prompt_seed", value: 0 },
        { name: "control_after_generate", value: "fixed" },
        { name: "enabled", value: enabled },
        { name: "fallback_prompt", value: "" },
        { name: "repeat_list", value: false },
        { name: "sequence_index", value: index },
    ];
    const node = {
        comfyClass: "WildcardLoRAPromptsV3", widgets,
        inputs: connected ? [{ name: "sequence_index", link: 42 }] : [],
        graph: { beforeChange() {}, afterChange() {}, setDirtyCanvas() {} },
        addWidget(type, name, value, callback, options) {
            const widget = { type, name, value, callback, options };
            widgets.push(widget);
            return widget;
        },
    };
    extension.nodeCreated(node);
    return { node, widget: (name) => widgets.find((widget) => widget.name === name), loadFile: () => fileChange() };
}

test("30 successful queue submissions serialize indices 0 to 29, independently of prompt_seed", () => {
    const { widget } = createNode();
    const submitted = [];
    for (let run = 0; run < 30; run++) {
        // ComfyUI serializes/submits first, then calls widget.afterQueued.
        submitted.push(widget("sequence_index").value);
        widget("prompt_seed").value = run * 123;
        widget("sequence_index").afterQueued();
    }
    assert.deepEqual(submitted, Array.from({ length: 30 }, (_, index) => index));
    assert.equal(widget("sequence_index").value, 30);
});

test("random, all-prompts and disabled modes leave the sequence index alone", () => {
    for (const options of [{ mode: "random prompt" }, { mode: "all prompts" }, { enabled: false }]) {
        const { widget } = createNode({ ...options, index: 7 });
        widget("sequence_index").afterQueued();
        assert.equal(widget("sequence_index").value, 7);
    }
});

test("Reset sequence resets the next submission without changing already submitted indices", () => {
    const { widget } = createNode({ index: 20 });
    const submitted = widget("sequence_index").value;
    widget("Reset sequence").callback();
    assert.equal(widget("sequence_index").value, 0);
    assert.equal(submitted, 20);
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 1);
});

test("loading a text file switches source and resets sequence", async () => {
    const { widget, loadFile } = createNode({ index: 30 });
    widget("Load .txt").callback();
    await loadFile();
    assert.equal(widget("prompts").value, "First\nSecond");
    assert.equal(widget("prompt_file").value, "");
    assert.equal(widget("sequence_index").value, 0);
});

test("buttons are not serialized, and legacy example widget values keep their positions", () => {
    const { node, widget } = createNode();
    const example = JSON.parse(readFileSync(new URL("../examples/wildcard-z-engineer.json", import.meta.url), "utf8"));
    const oldValues = example.nodes.find((node) => node.type === "WildcardLoRAPromptsV3").widgets_values;
    const serializable = node.widgets.filter((widget) => widget.serialize !== false);
    oldValues.forEach((value, index) => { serializable[index].value = value; });
    assert.equal(widget("mode").value, "random prompt");
    assert.equal(widget("control_after_generate").value, "randomize");
    assert.equal(widget("enabled").value, true);
    assert.equal(widget("fallback_prompt").value, "");
    assert.equal(widget("repeat_list").value, false);
    assert.equal(widget("sequence_index").value, 0);
    for (const name of ["Load .txt", "Reset sequence"]) {
        assert.equal(widget(name).serializeValue(), undefined);
        assert.equal(widget(name).options.serialize, false);
    }
});

test("connected index is owned by the upstream node", () => {
    const { widget } = createNode({ index: 7, connected: true });
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 7);
});

test("increment saturates instead of wrapping an exhausted sequence", () => {
    const { widget } = createNode({ index: 0xFFFFFFFF });
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 0xFFFFFFFF);
});
