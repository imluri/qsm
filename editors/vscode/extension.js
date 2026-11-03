"use strict";

const vscode = require("vscode");
const { spawn } = require("node:child_process");
const { parseCompilerError } = require("./diagnostics");
const gateHelp = require("./gate-help.json");

function activate(context) {
    const diagnostics = vscode.languages.createDiagnosticCollection("qsm");
    const output = vscode.window.createOutputChannel("QSM");
    const pending = new Map();
    context.subscriptions.push(diagnostics, output, {
        dispose() { for (const child of pending.values()) child.kill(); }
    });

    async function check(document) {
        if (!vscode.workspace.isTrusted || document.languageId !== "qsm" || document.uri.scheme !== "file") return;
        const key = document.uri.toString();
        pending.get(key)?.kill();
        const version = document.version;
        const config = vscode.workspace.getConfiguration("qsm", document.uri);
        const child = spawn(config.get("pythonPath", "python"), ["-m", "qsm", document.uri.fsPath, "--check"], {
            windowsHide: true,
            cwd: vscode.workspace.getWorkspaceFolder(document.uri)?.uri.fsPath,
            env: { ...process.env, PYTHONIOENCODING: "utf-8" }
        });
        pending.set(key, child);
        let stderr = "";
        child.stdout.resume();
        child.stderr.setEncoding("utf8");
        child.stderr.on("data", data => { stderr += data; });
        child.on("error", error => { stderr = `Unable to run QSM: ${error.message}. Set qsm.pythonPath to an interpreter with QSM installed.`; });
        child.on("close", code => {
            if (pending.get(key) !== child) return;
            pending.delete(key);
            if (document.isClosed || document.version !== version) return;
            if (code === 0) {
                diagnostics.delete(document.uri);
            } else {
                const error = parseCompilerError(stderr, document.uri.fsPath);
                const line = Math.min(error.line, document.lineCount - 1);
                const range = document.lineAt(line).range;
                const diagnostic = new vscode.Diagnostic(range, error.message, vscode.DiagnosticSeverity.Error);
                diagnostic.source = "QSM";
                diagnostics.set(document.uri, [diagnostic]);
                output.appendLine(stderr);
            }
        });
    }

    async function activeDocument() {
        const document = vscode.window.activeTextEditor?.document;
        if (!document || document.languageId !== "qsm") {
            vscode.window.showInformationMessage("Open a QSM file first.");
            return;
        }
        if (!await document.save()) return;
        return document.uri.scheme === "file" ? document : undefined;
    }

    context.subscriptions.push(
        vscode.commands.registerCommand("qsm.checkFile", async () => {
            const document = await activeDocument();
            if (document) await check(document);
        }),
        vscode.commands.registerCommand("qsm.runFile", async () => {
            const document = await activeDocument();
            if (!document || !vscode.workspace.isTrusted) return;
            const python = vscode.workspace.getConfiguration("qsm", document.uri).get("pythonPath", "python");
            const folder = vscode.workspace.getWorkspaceFolder(document.uri);
            const task = new vscode.Task(
                { type: "qsm", file: document.uri.fsPath }, folder || vscode.TaskScope.Global,
                "Run " + document.fileName.split(/[\\/]/).pop(), "QSM",
                new vscode.ProcessExecution(python, ["-m", "qsm", document.uri.fsPath]), []
            );
            await vscode.tasks.executeTask(task);
        }),
        vscode.workspace.onDidSaveTextDocument(document => {
            if (vscode.workspace.getConfiguration("qsm", document.uri).get("checkOnSave", true)) check(document);
        }),
        vscode.workspace.onDidCloseTextDocument(document => {
            const key = document.uri.toString();
            const child = pending.get(key);
            pending.delete(key);
            child?.kill();
            diagnostics.delete(document.uri);
        }),
        vscode.languages.registerHoverProvider("qsm", {
            provideHover(document, position) {
                const range = document.getWordRangeAtPosition(position);
                const help = range && gateHelp[document.getText(range)];
                return help ? new vscode.Hover(new vscode.MarkdownString(help), range) : undefined;
            }
        })
    );
}

module.exports = { activate };
