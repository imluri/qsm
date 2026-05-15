
<p align="center">
  <img src="logo.png" alt="QSM Logo" width="180"/>
</p>

# QSM: Quantum Lua Programming Language


QSM is a Lua-inspired quantum programming language for building quantum circuits and algorithms with Qiskit. It features a simple, extensible syntax and supports both quantum and classical control flow.



## Features
- **Lua-inspired syntax** for easy quantum programming
- **Qiskit integration** for quantum circuit and algorithm development
- **Quantum instructions:**
  - `qbit`, `creg`, `hadamard`/`h`, `x`, `y`, `z`, `s`, `t`, `cx`, `swap`, `mcz`, `measure`, `teleport`
- **Classical control flow:** `if`, `while`, `for`, assignments, and print
- **User-defined functions** and function calls
- **Multi-controlled Z gate** (Grover's diffusion)
- **Single-line comments** with `--`
- **Multiline comments** with `--[[ ... ]]--`
- **Extensible**: add new gates or syntax in `qsm/parser.py` and `qsm/compiler.py`
- **Full language reference:** see [`QSM_LANGUAGE.md`](QSM_LANGUAGE.md)

## Installation

1. Download the latest release source code from the [Releases page](https://github.com/astrixity/qsm/releases) and extract it.
2. Open a terminal in the extracted folder.
3. Install dependencies:
   ```sh
   pip install -r requirements.txt
   ```
4. (Optional) Install qsm as a command-line tool:
   ```sh
   pip install .
   ```

## Usage

Run a qsm script:
```sh
qsm <script.qsm>
```

Example:
```sh
qsm hello.qsm
```


## Example: Grover's Algorithm with Functions and Loops

```qsm
qbit q[4]
creg answer[4]

-- Create uniform superposition
for i = 0, 3 do
    hadamard q[i]
end

-- Oracle marks |1010>
function oracle()
    for i = 0, 3 do
        if i % 2 == 0 then
            z q[i]
        end
    end
end

function diffusion(n)
    for i = 0, n-1 do
        hadamard q[i]
        x q[i]
    end
    h q[n-1]
    mcz q[0..n-2], q[n-1]
    h q[n-1]
    for i = 0, n-1 do
        x q[i]
        hadamard q[i]
    end
end

diffusion(4)
oracle()
diffusion(4)

measure q[0] -> answer[0]
measure q[1] -> answer[1]
measure q[2] -> answer[2]
measure q[3] -> answer[3]
print "Grover output: ", answer
```

Output

```
$ qsm .\main.qsm
[qsm] Multi-controlled Z with 3 controls not fully implemented
[qsm] Multi-controlled Z with 3 controls not fully implemented

[qsm] Quantum Circuit:
     ┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌───┐┌─┐
q_0: ┤ H ├┤ H ├┤ X ├┤ H ├┤ Z ├┤ H ├┤ X ├┤ H ├┤ Z ├┤ H ├┤ X ├┤ H ├┤ Z ├┤ H ├┤ X ├┤ H ├┤M├
     ├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤└───┘└┬─┬┘└───┘└───┘└───┘└───┘└───┘└╥┘
q_1: ┤ H ├┤ H ├┤ X ├┤ X ├┤ H ├┤ H ├┤ X ├┤ X ├┤ H ├──────┤M├───────────────────────────╫─
     ├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤┌───┐ └╥┘  ┌─┐                      ║
q_2: ┤ H ├┤ H ├┤ X ├┤ X ├┤ H ├┤ Z ├┤ H ├┤ X ├┤ X ├┤ H ├──╫───┤M├──────────────────────╫─
     ├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤├───┤└┬─┬┘  ║   └╥┘                      ║
q_3: ┤ H ├┤ H ├┤ X ├┤ X ├┤ H ├┤ H ├┤ X ├┤ X ├┤ H ├─┤M├───╫────╫───────────────────────╫─
     └───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘└───┘ └╥┘   ║    ║                       ║
c: 4/═══════════════════════════════════════════════╩════╩════╩═══════════════════════╩═
                                                    3    1    2                       0
[qsm] Grover output:  1000
```
---

For a full language reference, advanced examples, and extension guide, see [`QSM_LANGUAGE.md`](QSM_LANGUAGE.md).

---

## Notes for Users

- qsm is designed for quantum programming with a familiar, Lua-like syntax.
- Use quantum instructions (`qbit`, `hadamard`, `x`, `z`, `y`, `s`, `t`, `cx`, `swap`, `measure`, `teleport`) to build quantum circuits.
- Classical control flow (`if`, `while`, `for`) is supported for structuring your quantum code.
- Comments start with `--` for single-line, or use `--[[ ... ]]--` for multiline comments.
- Not all Lua features are supported; focus is on quantum programming.
- See the `examples/` directory (if available) for more sample scripts.
- For advanced users: you can extend qsm by editing the parser and compiler in the `qsm/` directory.

For more information, see the code examples and documentation in this repository.
