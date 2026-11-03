<p align="center">
  <img src="logo.png" alt="QSM Logo" width="180"/>
</p>

# QSM: Quantum Lua Programming Language

QSM is a Lua-inspired language for building and simulating quantum circuits with
Qiskit. Write quantum instructions alongside classical expressions, loops and
functions, then run the file from a terminal or VS Code.

## Install

Download Python packages and the VS Code extension from the
[latest release](https://github.com/imluri/qsm/releases/latest).
For a downloaded wheel, run `python -m pip install /path/to/qsm-0.2.0-py3-none-any.whl`.

From the repository root:

```sh
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```sh
# macOS / Linux
source .venv/bin/activate
```

Install QSM, Qiskit and the Aer simulator together:

```sh
python -m pip install -e .
```

`python -m pip install -r requirements.txt` installs the same package and
dependencies. Use `python -m qsm` if the `qsm` command is not on your PATH.

## First circuit

Save this as `bell.qsm`:

```qsm
qbit q[2]
creg answer[2]

h q[0]
cx q[0], q[1]
measure q -> answer
print "Bell state:", answer
```

Run it:

```sh
qsm bell.qsm
qsm bell.qsm --shots 1024 --seed 42 --no-draw
```

A Bell pair produces `00` or `11`. Register output includes the bitstring and its
integer value, for example `[qsm] Bell state: 11 (3)`. With multiple shots, QSM
also prints the counts. Print expressions that reference measurements use the
first shot; bitstrings put the highest-index bit on the left.

## Language support

- Single-qubit gates, controlled gates, rotations, multi-controlled X/Z, reset,
  barriers, measurement and teleportation.
- Angle expressions such as `cp(-pi / 2^k) q[i], q[j]`.
- Whole-register and inclusive-range operands: `h q`, `x q[0..2]`.
- Arithmetic, comparisons, `and`/`or`/`not`, `true`/`false`/`nil`, and math functions.
- Nested `if`/`elseif`/`else`, `while`, and inclusive `for` loops with optional steps.
- Functions with expression arguments, individual qubit arguments and return values.
- Measurement feedback: `if answer[0] == 1 then ... end` builds a runtime conditional.
- Source filenames and line numbers in error messages.
- UTF-8 source files, including a UTF-8 byte order mark.

See the [language reference](QSM_LANGUAGE.md) for syntax and supported boundaries.

## Command-line tools

```sh
qsm examples/quantum_phase_estimation.qsm --check
qsm examples/grovers_algorithm.qsm --shots 1024 --seed 42 --no-draw
qsm examples/bell_state.qsm --qasm bell.qasm
qsm --help
```

`--check` compiles without simulation. `--qasm PATH` exports OpenQASM 3 without
simulation. `--debug` adds compilation details and full tracebacks.

## Examples

| Example | What it demonstrates |
| --- | --- |
| [Bell state](examples/bell_state.qsm) | Entanglement and measurement |
| [QFT round trip](examples/3-cubit_QFT.qsm) | Controlled phases; returns `101` |
| [Grover search](examples/grovers_algorithm.qsm) | Amplifies the marked state `1010` |
| [Phase estimation](examples/quantum_phase_estimation.qsm) | Estimates phase 1/2 as `100` |
| [Teleportation](examples/quantum_teleportation.qsm) | Measurement feedback; Bob's verification bit is zero |
| [Language features](examples/language_features.qsm) | Expressions, functions, descending loops and `elseif` |

Grover search is probabilistic; it is expected to return `1010` most of the time.

## VS Code

The [QSM extension](editors/vscode/README.md) adds syntax highlighting, snippets,
hover help, indentation, folding, run/check commands and compilation errors in
Problems. Open `editors/vscode` in VS Code and press F5 to try it. Set
`qsm.pythonPath` to your virtual environment's Python executable.

To install it locally, run `npx @vscode/vsce package` from `editors/vscode`, then
use **Extensions: Install from VSIX**. The extension is not published to the
Marketplace.

You can also install the prebuilt `qsm-language-0.2.0.vsix` attached to the release.

## Python API

```python
from qsm.compiler import QsmCompiler

compiler = QsmCompiler()
circuit = compiler.compile('qbit q[2]\nh q[0]\ncx q[0], q[1]\nmeasure q')
counts = compiler.run_simulation(shots=1024, seed=42, draw=False)
qasm = compiler.export_qasm()
```

The original `qsmCompiler` class name remains supported. Reusing a compiler for a
new source file clears the previous circuit and execution state.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
```

Editor tests:

```sh
cd editors/vscode
npm ci
npm test
```

Tests check expression/control-flow behavior, quantum gate matrices, simulation
results for every example, measurement feedback, teleportation, the CLI, and the
editor grammar. CI runs Python tests on Windows and Linux and editor tests on Linux.

QSM implements its own small expression evaluator; it does not execute arbitrary
Python statements. It is a circuit-building language, with the runtime feedback
boundaries documented in the reference, rather than a complete Lua implementation.
