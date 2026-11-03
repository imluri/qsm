# QSM Language Reference

QSM constructs Qiskit quantum circuits using a Lua-inspired syntax. Source files
use the `.qsm` extension and UTF-8 encoding. Write one statement per line. Block
indentation is for readability; `end` closes a block.

## Registers and indices

Declare registers at the top level with positive literal sizes:

```qsm
qbit q[4], alice, bob
creg answer[4], flag
```

Indices start at zero. Declarations must have unique names; arrays and scalars
cannot share a name. Register sizes and the total qubit/classical-bit counts are
limited to 128 each. Quantum instructions, math functions and constants are
reserved names. `result` is reserved for measurement output, but can be declared
as a classical register.

Quantum operands accept index expressions, whole arrays and inclusive ranges:

```qsm
h q
x q[0], q[2]
rz(pi / 4) q[i+1]
h q[0..n-1]
```

Single-qubit instructions apply separately to every selected target. Fixed-arity
controlled gates and swaps require individual qubits. Unknown names, invalid
indices, non-integer indices and out-of-range indices raise errors.

## Quantum instructions

Angle parameters go in parentheses immediately after the gate name and are
measured in radians. Commas separate parameters and operands.

| Instructions | Parameters | Operands |
| --- | --- | --- |
| `h`, `hadamard`, `x`, `y`, `z` | None | One or more qubits |
| `s`, `sdg`, `t`, `tdg`, `sx`, `sxdg`, `id` | None | One or more qubits |
| `rx`, `ry`, `rz`, `p` | One angle | One or more qubits |
| `u` | Three angles: theta, phi, lambda | One or more qubits |
| `cx`, `cy`, `cz`, `ch` | None | Control, target |
| `cp`, `crx`, `cry`, `crz` | One angle | Control, target |
| `rxx`, `ryy`, `rzz` | One angle | Two qubits |
| `swap` | None | Two qubits |
| `ccx` | None | Two controls, target |
| `cswap` | None | Control, two swap operands |
| `mcx`, `mcz` | None | Controls, then target |
| `reset` | None | One or more qubits |
| `barrier` | None | Selected qubits, or all qubits if omitted |
| `teleport` | None | Source, Bell-pair ancilla, destination |

Examples:

```qsm
rx(pi / 2) q[0]
cp(-pi / 2^k) q[i], q[j]
u(pi/2, 0, pi) q[0]
mcx q[0], q[1], q[2]
mcz q[0..n-2], q[n-1]
barrier
```

Controls and targets must be distinct. `mcz` flips the phase exactly when every
control and the target are in state 1. QSM implements it as H–MCX–H.

`teleport a, b, c` prepares a Bell pair between `b` and `c`, measures `a` and `b`,
and applies measurement-controlled X/Z corrections to `c`. Both `b` and `c` must
start in state 0. The shorthand allocates two additional classical bits and must
appear outside measurement-dependent conditionals. Use the explicit
[teleportation example](examples/quantum_teleportation.qsm) to control destinations
for the measurement bits yourself.

## Expressions and assignments

```qsm
n = 4
angle = -pi / (2^n)
ready = true
value = sqrt(4) + max(2, 3)
```

Supported values are numbers, strings, booleans and `nil`. Assignments store the
evaluated value. A variable must be defined before use.

| Kind | Syntax |
| --- | --- |
| Arithmetic | `+`, `-`, `*`, `/`, `//`, `%`, `^` (also `**`) |
| Comparisons | `==`, `~=` (also `!=`), `<`, `<=`, `>`, `>=` |
| Logic | `and`, `or`, `not` |
| Grouping | Parentheses |
| Constants | `pi`, `tau`, `e`, `true`, `false`, `nil` |
| Math functions | `sin`, `cos`, `tan`, `asin`, `acos`, `atan`, `sqrt`, `exp`, `log`, `ceil`, `floor` |
| Other functions | `abs`, `min`, `max`, `round`, `int`, `float` |

Multiplication/division precede addition/subtraction; powers are right-associative
and precede unary minus. Comparisons can be chained. `and` and `or` short-circuit.
Truthiness follows Python: zero, empty strings, false and nil are false.
Assignments target a single variable; register bits are written by measurement.

## Control flow

```qsm
if n > 2 and ready then
    h q[0]
elseif n == 2 then
    x q[0]
else
    z q[0]
end

for i = 0, n-1 do
    h q[i]
end

for i = n-1, 0, -1 do
    x q[i]
end

i = 0
while i < n do
    z q[i]
    i = i + 1
end
```

For-loop bounds are inclusive. The optional step defaults to 1 and cannot be zero.
Bounds and steps must be integers; a step pointing away from the endpoint yields
no iterations. The loop variable's previous value is restored after a `for` loop.
Blocks can be nested. Ordinary conditions, loop bounds and while conditions are
evaluated while building the circuit. Compilation allows at most 100,000 total
loop iterations and 100 nested function calls.

## Functions

```qsm
function entangle(a, b)
    h a
    cx a, b
end

function twice(value)
    return value * 2
end

entangle(q[0], q[1])
angle = twice(pi/4)
```

Arguments can be expressions, variables or individual qubits. Functions require
exactly the declared number of arguments and must be defined before use. They
execute with a local copy of the current variable environment. Local assignments
do not change outer variables; quantum operations change the shared circuit.
`return` exits the function and optionally supplies a value. Without it, the
return value is nil. Whole-register arguments, closures and variadic functions
are not supported.

## Measurement and runtime feedback

```qsm
measure q[0] -> answer[0]
measure q[1..3] -> answer[1..3]
measure q -> answer
```

Source and destination selections must have equal sizes. Without a destination,
QSM allocates a separate implicit classical bit per declared qubit; these do not
overwrite explicitly declared classical registers:

```qsm
qbit q[2]
h q[0]
measure q
print result
```

A measurement-dependent `if` builds a Qiskit runtime conditional:

```qsm
measure q[0] -> answer[0]
if answer[0] == 1 then
    x q[1]
else
    z q[1]
end
```

Runtime conditions support a single classical bit compared with 0 or 1 using
`==`, `~=` or `!=`. Scalar classical bits and reversed comparisons also work.
Runtime branches can contain gates, measurements, nested conditionals, static
loops and calls that emit gates. Assignments, returns, print statements,
function/register declarations and the teleport shorthand cannot depend on
measurement outcomes. While-loop conditions and gate angles must be known when
building the circuit. Measurement values cannot be assigned to ordinary
variables or used in arbitrary compile-time expressions.

## Printing and result order

```qsm
print "Result:", answer
print answer[i+1], 2 + 3 * 4
print("A comma, or -- in a string", answer[0])
```

Prints are displayed after simulation. Ordinary expressions capture their values
when the print statement is reached, including function arguments and loop
variables. Measurement-dependent expressions use the first simulation shot.
User function calls inside a measurement-dependent print expression are not
supported; ordinary arithmetic and built-in math functions are supported.

A scalar classical register prints a bit; a whole array prints its bitstring and
integer value, such as `0110 (6)`. Array index 0 is the least-significant bit, on
the right. Every declared classical register uses its own local indices,
regardless of its offset in the circuit. Unmeasured classical bits start at zero.

The generic `result` dictionary includes all circuit classical bits by global
index, including implicit measurement and teleportation bits. If a classical
register named `result` is declared, that name refers to that register instead.
With multiple named circuit registers, Qiskit's counts keys can contain spaces
between registers; the leftmost register contains the highest global indices.

## Comments

```qsm
-- A single-line comment
--[[ A multiline
comment ]]
--[[ The original delimiter is also accepted. ]]--
print "-- this remains a string"
```

Comment removal preserves original line numbers. Quoted strings support escape
sequences such as `\n`, `\"` and `\\`.

## CLI and Python API

```sh
qsm script.qsm --shots 1024 --seed 42 --no-draw
qsm script.qsm --check
qsm script.qsm --qasm circuit.qasm
```

`--check` validates parsing and circuit construction. `--qasm` exports OpenQASM 3.
Neither runs a simulation. Failed compilation/simulation returns a nonzero exit
status. `--debug` includes tracebacks.

```python
from qsm.compiler import QsmCompiler

compiler = QsmCompiler()
circuit = compiler.compile(source, filename="example.qsm")
counts = compiler.run_simulation(shots=1024, seed=42, draw=False)
text = compiler.export_qasm()
```

`qsmCompiler` remains an alias-compatible class name. `get_circuit()` returns the
current circuit. Calling `compile()` again resets all prior state. Use
`run_simulation()` before `execute_deferred_prints()` when measurements exist.

## Extending QSM

The instruction signatures live in `GATES` in `qsm/parser.py`. Most gates use the
generic `Gate` node and matching `QuantumCircuit` method; special instructions
are dispatched in `qsm/compiler.py`. Add quantum-result tests and keep the editor
grammar, snippets and hover help aligned with language changes.

Reference APIs: [Qiskit QuantumCircuit](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qiskit.circuit.QuantumCircuit),
[classical feedforward](https://quantum.cloud.ibm.com/docs/en/guides/classical-feedforward-and-control-flow),
and [OpenQASM 3 export](https://quantum.cloud.ibm.com/docs/en/api/qiskit/qasm3).
