import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import vm from "node:vm";

const source = readFileSync(new URL("../web/js/wildcard_prompts.js", import.meta.url), "utf8")
    .replace('import { app } from "../../../scripts/app.js";', "");

// The real frontend awaits the server between queue submissions, which lets
// queued microtasks run. Tests that submit several times must do the same.
const nextSubmission = () => new Promise((resolve) => setImmediate(resolve));

function makeGraph() {
    const graph = {
        nodes: [],
        links: new Map(),
        getNodeById: (id) => graph.nodes.find((node) => node.id === id) ?? null,
        beforeChange() {},
        afterChange() {},
        setDirtyCanvas() {},
    };
    return graph;
}

function link(graph, id, origin_id, origin_slot, target_id, target_slot = 0) {
    graph.links.set(id, { id, origin_id, origin_slot, target_id, target_slot });
}

function loadExtension() {
    let extension;
    let fileChange;
    const toasts = [];
    const picker = {
        files: [{ text: async () => "﻿First\nSecond" }],
        addEventListener: (event, callback) => { fileChange = callback; },
        click() {},
    };
    const root = makeGraph();
    const app = {
        rootGraph: root,
        canvas: { selected_nodes: {}, setDirty() {} },
        extensionManager: { toast: { warning: (title, options) => toasts.push({ title, options }) } },
        registerExtension: (value) => { extension = value; },
    };
    vm.runInNewContext(source, {
        app,
        document: { createElement: () => picker },
        window: { alert: (message) => { throw new Error(message); } },
        console: { warn() {} },
        queueMicrotask,
    });
    return { extension, app, root, toasts, loadFile: () => fileChange() };
}

function createNode({ mode = "sequential prompt", enabled = true, index = 0, graph, env = loadExtension(), id = 1 } = {}) {
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
    const inputs = ["mode", "enabled", "sequence_index"].map((name) => ({ name, widget: { name }, link: null }));
    const owner = graph ?? env.root;
    const node = {
        id, comfyClass: "WildcardLoRAPromptsV3", widgets, inputs, outputs: [{ name: "prompts", links: [] }], graph: owner,
        addWidget(type, name, value, callback, options) {
            const widget = { type, name, value, callback, options };
            widgets.push(widget);
            return widget;
        },
    };
    owner.nodes.push(node);
    env.extension.nodeCreated(node);
    const widget = (name) => widgets.find((item) => item.name === name);
    return { ...env, node, widget, input: (name) => inputs.find((item) => item.name === name) };
}

function createHost(env, subgraph, id, promoted) {
    const widgets = Object.entries(promoted).map(([name, value]) => ({ name, value }));
    const host = {
        id, graph: env.root, subgraph, isSubgraphNode: () => true, widgets,
        inputs: Object.keys(promoted).map((name) => ({ name, widget: { name }, link: null })),
        outputs: [],
        getWidgetFromSlot(slot) { return widgets.find((widget) => widget.name === slot.widget?.name); },
    };
    env.root.nodes.push(host);
    return { host, widget: (name) => widgets.find((item) => item.name === name) };
}

// A wildcard node inside a subgraph whose mode and sequence_index are promoted
// to every host instance. The interior widget values are deliberately stale.
function promotedSubgraph({ hosts = 1, innerMode = "random prompt" } = {}) {
    const env = loadExtension();
    const subgraph = makeGraph();
    const inner = createNode({ env, graph: subgraph, mode: innerMode, index: 99 });
    link(subgraph, 201, "-10", 0, inner.node.id);
    link(subgraph, 202, "-10", 1, inner.node.id);
    inner.input("mode").link = 201;
    inner.input("sequence_index").link = 202;
    const created = Array.from({ length: hosts }, (_, number) => createHost(
        env, subgraph, 50 + number, { mode: "sequential prompt", sequence_index: 10 * number },
    ));
    return { ...inner, hosts: created };
}

test("30 successful queue submissions serialize indices 0 to 29, independently of prompt_seed", async () => {
    const { widget } = createNode();
    const submitted = [];
    for (let run = 0; run < 30; run++) {
        // ComfyUI serializes/submits first, then calls widget.afterQueued.
        submitted.push(widget("sequence_index").value);
        widget("prompt_seed").value = run * 123;
        widget("sequence_index").afterQueued({ isPartialExecution: false });
        await nextSubmission();
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

test("Reset sequence resets the next submission without changing already submitted indices", async () => {
    const { widget } = createNode({ index: 20 });
    const submitted = widget("sequence_index").value;
    widget("Reset sequence").callback();
    assert.equal(widget("sequence_index").value, 0);
    assert.equal(submitted, 20);
    await nextSubmission();
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

test("an index fed by another node's output is owned upstream", () => {
    const { widget, input, root } = createNode({ index: 7 });
    root.nodes.push({ id: 9, type: "SomeCounter", widgets: [], outputs: [] });
    link(root, 42, 9, 0, 1);
    input("sequence_index").link = 42;
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 7);
});

test("an index fed by a legacy Primitive node advances that primitive", () => {
    const { widget, input, root } = createNode({ index: 7 });
    const primitive = { id: 9, type: "PrimitiveNode", widgets: [{ name: "value", value: 3 }], outputs: [] };
    root.nodes.push(primitive);
    link(root, 42, 9, 0, 1);
    input("sequence_index").link = 42;
    widget("sequence_index").afterQueued();
    assert.equal(primitive.widgets[0].value, 4);
    assert.equal(widget("sequence_index").value, 7);
});

test("increment saturates instead of wrapping an exhausted sequence", () => {
    const { widget } = createNode({ index: 0xFFFFFFFF });
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 0xFFFFFFFF);
});

test("repeated callbacks for one submission advance once (shared subgraph definitions)", async () => {
    const { widget } = createNode({ index: 4 });
    // The frontend visits a subgraph definition's nodes once per instance.
    widget("sequence_index").afterQueued();
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 5);
    await nextSubmission();
    widget("sequence_index").afterQueued();
    assert.equal(widget("sequence_index").value, 6);
});

test("a promoted sequence_index advances on the subgraph host, using the host's mode", async () => {
    const { widget, hosts } = promotedSubgraph({ innerMode: "random prompt" });
    for (let run = 0; run < 3; run++) {
        widget("sequence_index").afterQueued();
        await nextSubmission();
    }
    assert.equal(hosts[0].widget("sequence_index").value, 3);
    assert.equal(widget("sequence_index").value, 99, "the stale interior value is not used");
});

test("a promoted mode that is not sequential stops advancing, whatever the stale interior value", () => {
    const { widget, hosts } = promotedSubgraph({ innerMode: "sequential prompt" });
    hosts[0].widget("mode").value = "random prompt";
    widget("sequence_index").afterQueued();
    assert.equal(hosts[0].widget("sequence_index").value, 0);
});

test("every instance of a subgraph advances its own promoted index once per submission", async () => {
    const { widget, hosts } = promotedSubgraph({ hosts: 2 });
    for (let run = 0; run < 2; run++) {
        // One callback per instance, as the frontend does for shared definitions.
        widget("sequence_index").afterQueued();
        widget("sequence_index").afterQueued();
        await nextSubmission();
    }
    assert.deepEqual(hosts.map((host) => host.widget("sequence_index").value), [2, 12]);
});

test("Reset sequence resets promoted host indices", () => {
    const { widget, hosts } = promotedSubgraph({ hosts: 2 });
    widget("Reset sequence").callback();
    assert.deepEqual(hosts.map((host) => host.widget("sequence_index").value), [0, 0]);
});

test("partial runs advance only when this node feeds a selected node", async () => {
    const { node, widget, app, root } = createNode({ index: 2 });
    const unrelated = { id: 30, outputs: [] };
    const save = { id: 31, outputs: [] };
    root.nodes.push(unrelated, save);
    link(root, 70, 1, 0, 31);
    node.outputs[0].links = [70];

    app.canvas.selected_nodes = { 30: unrelated };
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    assert.equal(widget("sequence_index").value, 2);
    await nextSubmission();

    app.canvas.selected_nodes = { 31: save };
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    assert.equal(widget("sequence_index").value, 3);
});

test("partial runs advance only the selected shared subgraph instance", async () => {
    const { node, widget, hosts, app, root } = promotedSubgraph({ hosts: 2 });
    link(node.graph, 303, node.id, 0, "-20");
    node.outputs[0].links = [303];
    const save = { id: 80, graph: root, outputs: [] };
    root.nodes.push(save);
    link(root, 304, hosts[0].host.id, 0, save.id);
    hosts[0].host.outputs = [{ links: [304] }];

    app.canvas.selected_nodes = { 80: save };
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    assert.deepEqual(hosts.map((host) => host.widget("sequence_index").value), [1, 10]);
    await nextSubmission();

    app.canvas.selected_nodes = { 51: hosts[1].host };
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    assert.deepEqual(hosts.map((host) => host.widget("sequence_index").value), [1, 11]);
});

test("partial runs keep nested shared subgraph instances separate", () => {
    const { node, widget, hosts, app, root } = promotedSubgraph({ hosts: 2 });
    // Both existing hosts now live in one definition, instantiated twice.
    const parent = makeGraph();
    root.nodes.splice(0, root.nodes.length);
    for (const [number, { host }] of hosts.entries()) {
        host.graph = parent;
        parent.nodes.push(host);
        host.inputs[1].link = 410 + number;
        link(parent, 410 + number, "-10", 1, host.id, 1);
    }
    link(node.graph, 303, node.id, 0, "-20");
    node.outputs[0].links = [303];
    link(parent, 401, hosts[0].host.id, 0, "-20");
    hosts[0].host.outputs = [{ links: [401] }];
    const outerA = createHost({ root }, parent, 60, { mode: "sequential prompt", sequence_index: 3 });
    const outerB = createHost({ root }, parent, 61, { mode: "sequential prompt", sequence_index: 8 });
    app.canvas.selected_nodes = { 60: outerA.host };
    widget("sequence_index").afterQueued({ isPartialExecution: true });
    assert.equal(outerA.widget("sequence_index").value, 4);
    assert.equal(outerB.widget("sequence_index").value, 8);
});

function sharedPrimitive({ control = "fixed", primitiveFirst = false } = {}) {
    const env = loadExtension();
    const primitive = {
        id: 9, type: "PrimitiveNode", widgets: [
            { name: "value", value: 0 },
            { name: "control_after_generate", value: control },
        ], outputs: [],
    };
    if (primitiveFirst) env.root.nodes.push(primitive);
    const a = createNode({ env, id: 1 });
    const b = createNode({ env, id: 2 });
    if (!primitiveFirst) env.root.nodes.push(primitive);
    for (const [number, item] of [a, b].entries()) {
        link(env.root, 90 + number, 9, 0, item.node.id);
        item.input("sequence_index").link = 90 + number;
    }
    return { primitive, a, b, env };
}

test("two wildcard nodes sharing a fixed Primitive advance it once per submission", async () => {
    const { primitive, a, b } = sharedPrimitive();
    for (let run = 0; run < 3; run++) {
        a.widget("sequence_index").afterQueued();
        b.widget("sequence_index").afterQueued();
        assert.equal(primitive.widgets[0].value, run + 1);
        await nextSubmission();
    }
    a.widget("Reset sequence").callback();
    assert.equal(primitive.widgets[0].value, 0);
});

test("Primitive controls remain the owner of increment, decrement and randomize", async () => {
    for (const primitiveFirst of [false, true]) {
        for (const control of ["increment", "decrement", "randomize"]) {
            const { primitive, env } = sharedPrimitive({ control, primitiveFirst });
            primitive.widgets[0].value = 5;
            const expected = { increment: 6, decrement: 4, randomize: 17 }[control];
            let calls = 0;
            primitive.widgets[1].afterQueued = () => {
                calls++;
                primitive.widgets[0].value = control === "increment" ? primitive.widgets[0].value + 1
                    : control === "decrement" ? primitive.widgets[0].value - 1 : 17;
            };
            // Match ComfyUI's callback dispatch over nodes and their widgets.
            for (const node of env.root.nodes) {
                for (const widget of node.widgets ?? []) widget.afterQueued?.();
            }
            assert.equal(calls, 1);
            assert.equal(primitive.widgets[0].value, expected, `${control}, primitiveFirst=${primitiveFirst}`);
            assert.equal(primitive.widgets[1].value, control);
            await nextSubmission();
        }
    }
});

test("a custom Primitive value callback is not supplemented with another increment", () => {
    const { primitive, env } = sharedPrimitive();
    primitive.widgets[0].afterQueued = () => { primitive.widgets[0].value++; };
    for (const node of env.root.nodes) {
        for (const widget of node.widgets ?? []) widget.afterQueued?.();
    }
    assert.equal(primitive.widgets[0].value, 1);
});

test("execution status updates the reset label and warns once when the list is finished", async () => {
    const { node, widget, toasts } = createNode({ index: 21 });
    node.onExecuted({ wildcard_sequence: [{ index: 2, count: 20, prompt: 3, finished: false }] });
    assert.equal(widget("Reset sequence").label, "Reset sequence (last: 3/20)");

    for (let run = 0; run < 3; run++) {
        node.onExecuted({ wildcard_sequence: [{ index: 20 + run, count: 20, prompt: null, finished: true }] });
    }
    assert.equal(widget("Reset sequence").label, "Reset sequence (list finished, 20 prompts)");
    assert.equal(toasts.length, 1);
    assert.equal(toasts[0].title, "Wildcard sequence finished");

    toasts[0].options.action.onClick();
    assert.equal(widget("sequence_index").value, 0);
    assert.equal(widget("Reset sequence").label, "Reset sequence");
    node.onExecuted({ wildcard_sequence: [{ index: 20, count: 20, prompt: null, finished: true }] });
    assert.equal(toasts.length, 2, "a new finished sequence warns again after a reset");
});

test("onExecuted keeps calling an existing handler", () => {
    const env = loadExtension();
    const calls = [];
    const original = env.extension.nodeCreated;
    env.extension.nodeCreated = (node) => {
        node.onExecuted = (output) => calls.push(output);
        original.call(env.extension, node);
    };
    const { node } = createNode({ env });
    node.onExecuted({ text: ["x"] });
    assert.deepEqual(calls, [{ text: ["x"] }]);
});
