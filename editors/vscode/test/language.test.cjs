"use strict";
const { test, before } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { Registry, parseRawGrammar } = require("vscode-textmate");
const { loadWASM, OnigScanner, OnigString } = require("vscode-oniguruma");
const { parseCompilerError } = require("../diagnostics");
const base = path.resolve(__dirname, "..");
let grammar;

before(async () => {
    const wasm = fs.readFileSync(require.resolve("vscode-oniguruma/release/onig.wasm"));
    await loadWASM(wasm.buffer.slice(wasm.byteOffset, wasm.byteOffset + wasm.byteLength));
    const registry = new Registry({
        onigLib: Promise.resolve({ createOnigScanner: patterns => new OnigScanner(patterns), createOnigString: text => new OnigString(text) }),
        loadGrammar: async () => parseRawGrammar(fs.readFileSync(path.join(base, "syntaxes/qsm.tmLanguage.json"), "utf8"), "qsm.json")
    });
    grammar = await registry.loadGrammar("source.qsm");
});

function tokens(line, state) {
    return grammar.tokenizeLine(line, state);
}

test("strings preserve commas and comment markers", () => {
    const line = 'print "hello, -- not a comment", answer -- real comment';
    const result = tokens(line).tokens;
    const inside = result.find(t => t.startIndex <= line.indexOf("not") && t.endIndex > line.indexOf("not"));
    assert(inside.scopes.includes("string.quoted.double.qsm"));
    assert(result.at(-1).scopes.includes("comment.line.double-dash.qsm"));
});

test("multiline comments persist and close with either delimiter", () => {
    for (const end of ["]]", "]]--"]) {
        const start = tokens("--[[ comment");
        const middle = tokens("cp(pi/2) q[0], q[1]", start.ruleStack);
        assert(middle.tokens.every(t => t.scopes.includes("comment.block.qsm")));
        const close = tokens(end, middle.ruleStack);
        const next = tokens("h q[0]", close.ruleStack);
        assert(next.tokens[0].scopes.includes("support.function.quantum.qsm"));
    }
});

test("all documented quantum instructions have gate scopes", () => {
    const help = require("../gate-help.json");
    for (const name of Object.keys(help).filter(n => n !== "qbit" && n !== "creg")) {
        assert(tokens(name + " q[0]").tokens[0].scopes.includes("support.function.quantum.qsm"), name);
    }
});

test("operators, numeric ranges and Lua literals are recognized", () => {
    const line = "if i ~= 0 and true then";
    const result = tokens(line).tokens;
    assert(result.some(t => line.slice(t.startIndex, t.endIndex) === "~=" && t.scopes.includes("keyword.operator.qsm")));
    assert(result.some(t => line.slice(t.startIndex, t.endIndex) === "true" && t.scopes.includes("constant.language.qsm")));
    const range = "mcz q[0..2], q[3]";
    const numeric = tokens(range).tokens.filter(t => t.scopes.includes("constant.numeric.qsm")).map(t => range.slice(t.startIndex, t.endIndex));
    assert.deepEqual(numeric, ["0", "2", "3"]);
});

test("compiler diagnostics preserve Windows and POSIX paths", () => {
    assert.deepEqual(parseCompilerError("C:\\Users\\test\\script.qsm:12: Unknown variable 'n'\r\n", "fallback"), {
        path: "C:\\Users\\test\\script.qsm", line: 11, message: "Unknown variable 'n'"
    });
    assert.equal(parseCompilerError("/tmp/a.qsm:2: Missing end", "fallback").line, 1);
    assert.equal(parseCompilerError("Python is unavailable", "fallback").path, "fallback");
});

test("extension contributions resolve to existing files and commands", () => {
    const manifest = require("../package.json");
    for (const entry of [...manifest.contributes.grammars, ...manifest.contributes.snippets]) {
        assert(fs.existsSync(path.join(base, entry.path)));
    }
    assert(fs.existsSync(path.join(base, manifest.main)));
    const extension = fs.readFileSync(path.join(base, manifest.main), "utf8");
    for (const command of manifest.contributes.commands) assert(extension.includes(command.command));
});

test("snippets provide editable placeholders and valid block endings", () => {
    const snippets = require("../snippets/qsm.json");
    for (const [name, snippet] of Object.entries(snippets)) {
        assert(snippet.prefix, name);
        assert(Array.isArray(snippet.body) && snippet.body.length > 0, name);
        assert(snippet.body.join("\n").includes("${1:"), name);
    }
});
