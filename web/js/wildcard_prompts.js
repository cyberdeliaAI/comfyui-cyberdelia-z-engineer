import { app } from "../../../scripts/app.js";

const NODE_CLASS = "WildcardLoRAPromptsV3";
const SEQUENTIAL = "sequential prompt";
const RESET_LABEL = "Reset sequence";
const MAX_INDEX = 0xFFFFFFFF;
const MAX_DEPTH = 16;
// LiteGraph ids of the input and output boundary nodes inside a subgraph.
const SUBGRAPH_INPUT_ID = "-10";
const SUBGRAPH_OUTPUT_ID = "-20";
// A widget may be shared by several wildcard nodes. afterQueued callbacks for
// one submission run synchronously; the next server submission yields first.
const advancingWidgets = new WeakSet();
const primitiveOwners = new WeakMap();

function rootGraph() {
    return app.rootGraph ?? app.graph ?? null;
}

function findWidget(node, name) {
    return node?.widgets?.find((widget) => widget.name === name) ?? null;
}

function getLink(graph, linkId) {
    if (linkId == null || !graph?.links) return null;
    return graph.links.get?.(linkId) ?? graph.links[linkId] ?? null;
}

function isSubgraphNode(node) {
    return typeof node?.isSubgraphNode === "function" && node.isSubgraphNode() && !!node.subgraph;
}

// Every subgraph node, anywhere in the workflow, that uses `subgraph` as its definition.
function hostsOf(subgraph) {
    const hosts = [];
    const visited = new Set();
    const visit = (graph) => {
        if (!graph || visited.has(graph)) return;
        visited.add(graph);
        for (const node of graph.nodes ?? []) {
            if (!isSubgraphNode(node)) continue;
            if (node.subgraph === subgraph) hosts.push(node);
            visit(node.subgraph);
        }
    };
    visit(rootGraph());
    return hosts;
}

// Each chain lists subgraph host nodes from the innermost to the outermost
// level. A node in the root graph has one empty chain. Subgraph instances share
// their definition's nodes, so one wildcard node can have several chains.
function hostChains(graph, depth = 0) {
    const root = rootGraph();
    if (!graph || !root || graph === root || depth > MAX_DEPTH) return [[]];
    const chains = [];
    for (const host of hostsOf(graph)) {
        for (const outer of hostChains(host.graph, depth + 1)) chains.push([host, ...outer]);
    }
    return chains.length ? chains : [[]];
}

function slotWidget(node, input) {
    return node.getWidgetFromSlot?.(input) ?? findWidget(node, input.widget?.name ?? input.name);
}

// The widget whose value ComfyUI actually receives for an input. A promoted
// input is fed by the subgraph boundary, so its value lives on the host node and
// the interior widget is stale. Returns null when another node's output feeds
// the input: that value is owned upstream and must not be changed here.
function slotSource(node, input, chain, depth = 0) {
    if (input.link == null) return slotWidget(node, input);
    if (depth > MAX_DEPTH) return null;
    const link = getLink(node.graph, input.link);
    if (!link) return null;
    if (String(link.origin_id) === SUBGRAPH_INPUT_ID) {
        const host = chain[0];
        const hostInput = host?.inputs?.[link.origin_slot];
        return hostInput ? slotSource(host, hostInput, chain.slice(1), depth + 1) : null;
    }
    const origin = node.graph?.getNodeById?.(link.origin_id);
    // Legacy Primitive nodes keep the value in their own widget.
    if (origin?.type === "PrimitiveNode") {
        const widget = origin.widgets?.[0];
        if (widget) primitiveOwners.set(widget, origin);
        return widget ?? null;
    }
    return null;
}

function sourceWidget(node, name, chain) {
    const input = node.inputs?.find((slot) => slot.widget?.name === name || slot.name === name);
    return input ? slotSource(node, input, chain) : findWidget(node, name);
}

function sequenceTargets(node) {
    const targets = new Set();
    for (const chain of hostChains(node.graph)) {
        const widget = sourceWidget(node, "sequence_index", chain);
        if (widget) targets.add(widget);
    }
    return targets;
}

function setValue(widget, value) {
    widget.value = value;
    widget.callback?.(value);
}

function redraw(node) {
    node.graph?.setDirtyCanvas?.(true, true);
    app.canvas?.setDirty?.(true, true);
}

function statusLabel(status) {
    if (!status || !Number.isInteger(status.count)) return RESET_LABEL;
    if (status.finished) return `${RESET_LABEL} (list finished, ${status.count} prompts)`;
    return `${RESET_LABEL} (last: ${status.prompt}/${status.count})`;
}

function showStatus(node, status) {
    if (node.__wildcardResetButton) node.__wildcardResetButton.label = statusLabel(status);
    redraw(node);
}

function resetSequence(node, recordChange = true) {
    const targets = sequenceTargets(node);
    if (!targets.size) return;
    if (recordChange) node.graph?.beforeChange?.();
    for (const widget of targets) setValue(widget, 0);
    if (recordChange) node.graph?.afterChange?.();
    node.__wildcardFinishedNotified = false;
    showStatus(node, null);
}

function notifyFinished(node, status) {
    const title = "Wildcard sequence finished";
    const description = `All ${status.count} prompt(s) were used, so this run skipped the nodes that use the prompt. Reset the sequence or turn on repeat_list.`;
    try {
        const toast = app.extensionManager?.toast;
        if (typeof toast?.warning === "function") {
            toast.warning(title, {
                description,
                action: { label: RESET_LABEL, onClick: () => resetSequence(node) },
            });
        } else if (typeof toast?.add === "function") {
            toast.add({ severity: "warn", summary: title, detail: description, life: 8000 });
        }
    } catch (error) {
        console.warn("[Wildcard Prompts] Could not show the sequence notice", error);
    }
    console.warn(`[Wildcard Prompts] ${title}: ${description}`);
}

// "Queue selected output nodes" runs only the selected outputs and what feeds
// them. Advance only when this node feeds one of them, so no prompt is skipped.
function feedsSelectedNodes(node, chain) {
    const selected = new Set(Object.values(app.canvas?.selected_nodes ?? {}));
    if (!selected.size) return true;
    const visited = new Set();
    const stack = [{ node, chain }];
    while (stack.length) {
        const { node: current, chain: currentChain } = stack.pop();
        if (!current || visited.has(current)) continue;
        visited.add(current);
        if (selected.has(current)) return true;
        for (const output of current.outputs ?? []) {
            for (const linkId of output.links ?? []) {
                const link = getLink(current.graph, linkId);
                if (!link) continue;
                if (String(link.target_id) === SUBGRAPH_OUTPUT_ID) {
                    // Leave this concrete instance, not every host of its shared
                    // definition. Otherwise a selected A also advances an idle B.
                    if (currentChain[0]) stack.push({ node: currentChain[0], chain: currentChain.slice(1) });
                } else {
                    stack.push({ node: current.graph?.getNodeById?.(link.target_id), chain: currentChain });
                }
            }
        }
    }
    return false;
}

function primitiveControlsIndex(widget) {
    const owner = primitiveOwners.get(widget);
    if (!owner) return false;
    const control = owner.widgets?.find((item) => item.name === "control_after_generate") ?? owner.widgets?.[1];
    // Respect before/after-generate controls regardless of node traversal order,
    // and leave custom value callbacks in charge of their own counter.
    return typeof widget.beforeQueued === "function" || typeof widget.afterQueued === "function"
        || ["increment", "decrement", "randomize", "increment-wrap"].includes(control?.value);
}

function advanceSequence(node, options) {
    // The frontend visits a subgraph definition's nodes once per instance, so
    // one queue submission can call this several times. Advance only once.
    if (node.__wildcardAdvancing) return;
    node.__wildcardAdvancing = true;
    queueMicrotask(() => { node.__wildcardAdvancing = false; });

    const targets = new Set();
    for (const chain of hostChains(node.graph)) {
        if (options?.isPartialExecution && !feedsSelectedNodes(node, chain)) continue;
        // Fall back to the local widget when another node feeds mode or enabled.
        const mode = sourceWidget(node, "mode", chain) ?? findWidget(node, "mode");
        const enabled = sourceWidget(node, "enabled", chain) ?? findWidget(node, "enabled");
        if (mode?.value !== SEQUENTIAL || enabled?.value === false) continue;
        // Null means a connected node owns the index (for example an API counter).
        const index = sourceWidget(node, "sequence_index", chain);
        if (index) targets.add(index);
    }
    for (const widget of targets) {
        if (advancingWidgets.has(widget) || primitiveControlsIndex(widget)) continue;
        const value = Number(widget.value);
        if (Number.isSafeInteger(value) && value >= 0) {
            advancingWidgets.add(widget);
            queueMicrotask(() => { advancingWidgets.delete(widget); });
            setValue(widget, Math.min(value + 1, MAX_INDEX));
        }
    }
    if (targets.size) redraw(node);
}

function frontendButton(node, name, callback) {
    const widget = node.addWidget("button", name, null, callback, { serialize: false });
    widget.serialize = false;
    widget.options ??= {};
    widget.options.serialize = false;
    widget.serializeValue = () => undefined;
    return widget;
}

app.registerExtension({
    name: "cyberdelia.wildcard.loadPrompts",
    nodeCreated(node) {
        if (node.comfyClass !== NODE_CLASS) return;

        const index = findWidget(node, "sequence_index");
        if (index) {
            const previousAfterQueued = index.afterQueued;
            // afterQueued runs after serialization and each successful
            // submission, once per entry in Run's batch count, not after execution.
            index.afterQueued = function (...args) {
                const result = previousAfterQueued?.apply(this, args);
                advanceSequence(node, args[0]);
                return result;
            };
        }

        const previousOnExecuted = node.onExecuted;
        node.onExecuted = function (output, ...rest) {
            const result = previousOnExecuted?.call(this, output, ...rest);
            const status = output?.wildcard_sequence?.[0];
            if (status) {
                showStatus(node, status);
                if (status.finished && !node.__wildcardFinishedNotified) {
                    node.__wildcardFinishedNotified = true;
                    notifyFinished(node, status);
                } else if (!status.finished) {
                    node.__wildcardFinishedNotified = false;
                }
            }
            return result;
        };

        frontendButton(node, "Load .txt", () => {
            const picker = document.createElement("input");
            picker.type = "file";
            picker.accept = ".txt,text/plain";
            picker.addEventListener("change", async () => {
                const file = picker.files?.[0];
                if (!file) return;
                try {
                    const text = await file.text();
                    const prompts = findWidget(node, "prompts");
                    const path = findWidget(node, "prompt_file");
                    if (!prompts) throw new Error("The prompts field is unavailable.");
                    node.graph?.beforeChange?.();
                    setValue(prompts, text.replace(/^﻿/, ""));
                    // Loading a browser file switches back to the pasted-text source.
                    if (path) setValue(path, "");
                    resetSequence(node, false);
                    node.graph?.afterChange?.();
                    redraw(node);
                } catch (error) {
                    window.alert(`Could not load the prompt file: ${error.message}`);
                }
            }, { once: true });
            picker.click();
        });
        node.__wildcardResetButton = frontendButton(node, RESET_LABEL, () => resetSequence(node));
    },
});
