# QSM for Visual Studio Code

Language support for `.qsm` quantum programs:

- Syntax highlighting, comments, bracket matching, indentation and folding.
- Snippets for circuits, Bell pairs, loops, functions and measurement feedback.
- Hover help for quantum instructions.
- **QSM: Run File** and **QSM: Check File** commands.
- Compilation errors in Problems after saving a file.

## Try the extension

1. Install QSM from the repository: `python -m pip install -e .`.
2. Open this `editors/vscode` folder in VS Code.
3. Press F5 to open an Extension Development Host.
4. Open a `.qsm` file in that window.

For a virtual environment, set **QSM: Python Path** to its Python executable,
for example `C:\path\to\qsm\.venv\Scripts\python.exe` on Windows or
`/path/to/qsm/.venv/bin/python` on macOS/Linux. The extension defaults to `python`
from VS Code's environment. It does not automatically select the Python extension's interpreter.

Check on save can be disabled with `"qsm.checkOnSave": false`. Run and check
commands save the file first. Checking compiles the file without simulation.
The first compilation error is shown; correct it and save to see the next error.
Execution features require a trusted workspace.

## Install as a package

From this folder, run `npx @vscode/vsce package`, then use **Extensions: Install
from VSIX** to install the resulting file. This extension has not been published
to the Marketplace.

## Tests

Run `npm ci` and `npm test` in this folder. Tests cover the actual TextMate grammar,
snippets, and compilation error parsing. The VS Code UI should also be checked
in the Extension Development Host before publishing.
