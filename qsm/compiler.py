"""Compile QSM into Qiskit circuits and simulate them with Qiskit Aer."""

from __future__ import annotations

import ast
import math
import operator
import re
import sys
from dataclasses import dataclass

from qiskit import ClassicalRegister, QuantumCircuit, QuantumRegister, qasm3, transpile

from qsm.parser import (
    CRegDecl, CX, FunctionCall, FunctionDef, GATES, Gate, Hadamard, MCZGate,
    Measure, QBitDecl, SGate, SwapGate, TGate, Teleport, XGate, YGate, ZGate,
    parse_expression, qsmParser, split_arguments,
)

MAX_QUBITS = 128
MAX_CBITS = 128
MAX_ITERATIONS = 100000
MAX_CALL_DEPTH = 100

_BINARY = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul,
           ast.Div: operator.truediv, ast.FloorDiv: operator.floordiv,
           ast.Mod: operator.mod, ast.Pow: operator.pow}
_COMPARE = {ast.Eq: operator.eq, ast.NotEq: operator.ne, ast.Lt: operator.lt,
            ast.LtE: operator.le, ast.Gt: operator.gt, ast.GtE: operator.ge}
_BUILTINS = {name: getattr(math, name) for name in
             ("sin", "cos", "tan", "asin", "acos", "atan", "sqrt", "exp", "log", "ceil", "floor")}
_BUILTINS.update(abs=abs, min=min, max=max, round=round, int=int, float=float)


@dataclass(frozen=True)
class _QubitRef:
    name: str


class _Return(Exception):
    def __init__(self, value):
        self.value = value


class qsmCompiler:
    """Build a circuit with compile(), then run_simulation() or export_qasm()."""

    def __init__(self, debug=False):
        self.debug = debug
        self.parser = qsmParser()
        self._reset()

    def _reset(self):
        self.qubit_map, self.cbit_map = {}, {}
        self.qreg, self.creg = [], []
        self._quantum_names, self._classical_names = set(), set()
        self._default_bits = {}
        self.qc = None
        self.env = {"pi": math.pi, "tau": math.tau, "e": math.e}
        self.variables = {}
        self.deferred_prints = []
        self.has_measurements = False
        self._iterations = self._call_depth = self._dynamic_depth = 0
        self.filename = "<qsm>"

    def compile(self, code, filename="<qsm>"):
        self._reset()
        self.filename = filename
        nodes = self.parser.parse(code, filename=filename)
        self._allocate_registers(nodes)
        registers = []
        if self.qreg:
            registers.append(QuantumRegister(len(self.qreg), "q"))
        if self.creg:
            registers.append(ClassicalRegister(len(self.creg), "c"))
        self.qc = QuantumCircuit(*registers)
        for node in nodes:
            self._emit(node)
        self._debug_print("Built {} qubits, {} classical bits, {} operations".format(
            self.qc.num_qubits, self.qc.num_clbits, len(self.qc.data)))
        return self.qc

    def _debug_print(self, message):
        if self.debug:
            print("[qsm:debug] " + message)

    def _allocate_registers(self, nodes):
        implicit = False

        def walk(items, nested=False):
            nonlocal implicit
            for node in items:
                if isinstance(node, (QBitDecl, CRegDecl)):
                    try:
                        self._allocate_declaration(node, nested)
                    except (SyntaxError, ValueError) as exc:
                        exc.qsm_location = "{}:{}".format(self.filename, node.lineno)
                        raise
                elif isinstance(node, Measure) and node.classical_target is None:
                    implicit = True
                if hasattr(node, "body"):
                    walk(node.body, True)
                if hasattr(node, "orelse"):
                    walk(node.orelse, True)
        walk(nodes)
        if implicit:
            if len(self.creg) + len(self.qreg) > MAX_CBITS:
                raise ValueError("Implicit measurements exceed the classical bit limit")
            for i, name in enumerate(self.qreg):
                self._default_bits[name] = len(self.creg)
                self.creg.append("__measure[{}]".format(i))

    def _allocate_declaration(self, node, nested):
        if nested:
            raise SyntaxError("Declare registers at the top level")
        quantum = isinstance(node, QBitDecl)
        mapping = self.qubit_map if quantum else self.cbit_map
        names = self.qreg if quantum else self.creg
        bases = self._quantum_names if quantum else self._classical_names
        other = self._classical_names if quantum else self._quantum_names
        new_bases = {name.split("[")[0] for name in node.targets}
        reserved = set(_BUILTINS) | set(GATES) | {"pi", "tau", "e"}
        if new_bases & reserved or (quantum and "result" in new_bases):
            raise ValueError("Register names cannot use reserved language names")
        if new_bases & (bases | other) or len(set(node.targets)) != len(node.targets):
            raise ValueError("Register names must be unique")
        # A scalar and an array cannot share a base within one declaration.
        if any(base in node.targets and any(n.startswith(base + "[") for n in node.targets)
               for base in new_bases):
            raise ValueError("A scalar and an array cannot share a name")
        limit = MAX_QUBITS if quantum else MAX_CBITS
        if len(names) + len(node.targets) > limit:
            raise ValueError("At most {} {} bits are supported".format(limit, "quantum" if quantum else "classical"))
        bases.update(new_bases)
        for name in node.targets:
            mapping[name] = len(names)
            names.append(name)

    def _emit(self, node):
        try:
            self._dispatch(node)
        except _Return:
            raise
        except (SyntaxError, NameError, ValueError, TypeError, IndexError, ZeroDivisionError, RuntimeError) as exc:
            if not getattr(exc, "qsm_location", None):
                line = getattr(node, "lineno", 1)
                exc.qsm_location = "{}:{}".format(self.filename, line)
            raise

    def _dispatch(self, node):
        if isinstance(node, (QBitDecl, CRegDecl)):
            return
        single = {Hadamard: "h", XGate: "x", YGate: "y", ZGate: "z", SGate: "s", TGate: "t"}
        if type(node) in single:
            for q in self._expand_reference(node.target, quantum=True):
                getattr(self.qc, single[type(node)])(self.qubit_map[q])
        elif isinstance(node, CX):
            self.qc.cx(self._q(node.ctrl), self._q(node.targ))
        elif isinstance(node, SwapGate):
            self.qc.swap(self._q(node.q1), self._q(node.q2))
        elif isinstance(node, MCZGate):
            self._multi_control("mcz", split_arguments(node.controls), node.target)
        elif isinstance(node, Gate):
            self._gate(node)
        elif isinstance(node, Measure):
            qubits = self._expand_reference(node.target, True)
            if node.classical_target is None:
                cbits = [self._default_bits[q] for q in qubits]
            else:
                cbits = [self.cbit_map[c] for c in self._expand_reference(node.classical_target, False)]
            if len(qubits) != len(cbits):
                raise ValueError("Measurement register sizes differ")
            for q, c in zip(qubits, cbits):
                self.qc.measure(self.qubit_map[q], c)
            self.has_measurements = True
        elif isinstance(node, Teleport):
            self._teleport(node)
        elif isinstance(node, FunctionDef):
            if self._dynamic_depth:
                raise SyntaxError("Function definitions cannot depend on measurements")
            self._check_variable(node.name)
            self.env[node.name] = node
        elif isinstance(node, FunctionCall):
            self._call_function(node.name, [self._eval_expr(arg) for arg in node.args])
        elif isinstance(node, ast.Assign):
            if self._dynamic_depth:
                raise SyntaxError("Assignments cannot depend on measurements")
            self._check_variable(node.targets[0].id)
            self.env[node.targets[0].id] = self._eval_expr(node.value)
        elif isinstance(node, ast.Return):
            if not self._call_depth:
                raise SyntaxError("'return' is only valid inside a function")
            if self._dynamic_depth:
                raise SyntaxError("Function returns cannot depend on measurements")
            raise _Return(self._eval_expr(node.value) if node.value else None)
        elif isinstance(node, ast.For):
            bounds = [self._integer(self._eval_expr(a), "Loop bound") for a in node.iter.args]
            start, stop = bounds[:2]
            step = bounds[2] if len(bounds) == 3 else 1
            if step == 0:
                raise ValueError("For-loop step cannot be zero")
            name = node.target.id
            self._check_variable(name)
            missing = object()
            old = self.env.get(name, missing)
            try:
                for value in range(start, stop + (1 if step > 0 else -1), step):
                    self._tick()
                    self.env[name] = value
                    for child in node.body:
                        self._emit(child)
            finally:
                if old is missing:
                    self.env.pop(name, None)
                else:
                    self.env[name] = old
        elif isinstance(node, ast.While):
            if self._uses_classical(node.test):
                raise SyntaxError("While-loop conditions must be known at compile time")
            while self._eval_expr(node.test):
                self._tick()
                for child in node.body:
                    self._emit(child)
        elif isinstance(node, ast.If):
            self._if(node)
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Call) and node.value.func.id == "print":
            if self._dynamic_depth:
                raise SyntaxError("Print statements cannot depend on measurements; print after the conditional")
            args = []
            for arg in node.value.args:
                # Freeze ordinary expressions now; measurement expressions use the final sample.
                args.append(arg if self._uses_classical(arg) else ast.Constant(value=self._eval_expr(arg)))
            self.deferred_prints.append((args, self.env.copy()))
        else:
            raise SyntaxError("Unsupported statement: " + type(node).__name__)

    def _check_variable(self, name):
        if name in self._quantum_names | self._classical_names or name == "result":
            raise ValueError("'{}' is reserved for a register or measurement results".format(name))
        if name in GATES or name in _BUILTINS or name in ("pi", "tau", "e", "print"):
            raise ValueError("'{}' is a reserved language name".format(name))

    def _tick(self):
        self._iterations += 1
        if self._iterations > MAX_ITERATIONS:
            raise RuntimeError("Compile-time loop iteration limit exceeded")

    def _gate(self, node):
        if node.name in ("mcx", "mcz"):
            self._multi_control(node.name, node.targets[:-1], node.targets[-1])
            return
        params = [self._eval_expr(p) for p in node.params]
        if any(isinstance(p, bool) or not isinstance(p, (int, float)) or not math.isfinite(p) for p in params):
            raise ValueError("Gate angles must be finite numbers")
        targets = [self.qubit_map[q] for target in node.targets for q in self._expand_reference(target, True)]
        if node.name == "barrier":
            self.qc.barrier(*(targets or range(self.qc.num_qubits)))
        elif GATES[node.name][1] is None:
            for target in targets:
                getattr(self.qc, node.name)(*params, target)
        else:
            if len(targets) != GATES[node.name][1]:
                raise ValueError("Gate '{}' requires individual qubits".format(node.name))
            getattr(self.qc, node.name)(*params, *targets)

    def _multi_control(self, name, controls, target):
        controls = [self.qubit_map[q] for ref in controls for q in self._expand_reference(ref, True)]
        target = self._q(target)
        if len(set(controls + [target])) != len(controls) + 1:
            raise ValueError("Controls and target must be distinct qubits")
        if name == "mcz":
            self.qc.h(target)
        if controls:
            self.qc.mcx(controls, target)
        else:
            self.qc.x(target)
        if name == "mcz":
            self.qc.h(target)

    @staticmethod
    def _integer(value, label):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(label + " must be an integer")
        return value

    def _expand_reference(self, reference, quantum):
        mapping = self.qubit_map if quantum else self.cbit_map
        names = self.qreg if quantum else list(self.cbit_map)
        reference = reference.strip()
        alias = self.env.get(reference)
        if quantum and isinstance(alias, _QubitRef):
            reference = alias.name
        if reference in mapping:
            return [reference]
        match = re.fullmatch(r"([A-Za-z_]\w*)\[\s*(.+)\s*\]", reference)
        if match:
            base, index = match.groups()
            if ".." in index:
                start, stop = index.split("..", 1)
                start, stop = self._eval_expr_str(start), self._eval_expr_str(stop)
                if stop - start + 1 > len(mapping):
                    raise NameError("Register range '{}' exceeds the declared register".format(reference))
                resolved = ["{}[{}]".format(base, i) for i in range(start, stop + 1)]
            else:
                resolved = ["{}[{}]".format(base, self._eval_expr_str(index))]
        else:
            resolved = [name for name in names if name.startswith(reference + "[")]
        if not resolved and match and ".." in match[2] and match[1] in (self._quantum_names if quantum else self._classical_names):
            return []
        if not resolved or any(name not in mapping for name in resolved):
            raise NameError("{} '{}' is not declared or is out of range".format("Qubit" if quantum else "Classical bit", reference))
        return resolved

    def _q(self, name):
        resolved = self._expand_reference(name, True)
        if len(resolved) != 1:
            raise ValueError("Expected an individual qubit: " + name)
        return self.qubit_map[resolved[0]]

    def _c(self, name):
        resolved = self._expand_reference(name, False)
        if len(resolved) != 1:
            raise ValueError("Expected an individual classical bit: " + name)
        return self.cbit_map[resolved[0]]

    def _eval_expr_str(self, source):
        return self._integer(self._eval_expr(parse_expression(source)), "Register index")

    def _eval_expr(self, node, env=None):
        env = self.env if env is None else env
        evaluate = lambda child: self._eval_expr(child, env)
        if isinstance(node, ast.Constant):
            return node.value
        if isinstance(node, ast.Name):
            if node.id in env:
                return env[node.id]
            if node.id in self.qubit_map:
                return _QubitRef(node.id)
            if node.id in self._classical_names or node.id == "result":
                raise ValueError("Measurement values are available at runtime; use a bit comparison in 'if'")
            raise NameError("Unknown variable '{}'".format(node.id))
        if isinstance(node, ast.Subscript):
            index = self._integer(evaluate(node.slice), "Register index")
            if isinstance(node.value, ast.Name) and node.value.id in self._quantum_names:
                name = "{}[{}]".format(node.value.id, index)
                self._q(name)
                return _QubitRef(name)
            value = evaluate(node.value)
            if not isinstance(value, dict) or index not in value:
                raise IndexError("Register index {} is out of range".format(index))
            return value[index]
        if isinstance(node, ast.BinOp) and type(node.op) in _BINARY:
            return _BINARY[type(node.op)](evaluate(node.left), evaluate(node.right))
        if isinstance(node, ast.UnaryOp):
            operations = {ast.USub: operator.neg, ast.UAdd: operator.pos, ast.Not: operator.not_}
            if type(node.op) in operations:
                return operations[type(node.op)](evaluate(node.operand))
        if isinstance(node, ast.BoolOp):
            value = evaluate(node.values[0])
            for child in node.values[1:]:
                if isinstance(node.op, ast.And) and not value or isinstance(node.op, ast.Or) and value:
                    return value
                value = evaluate(child)
            return value
        if isinstance(node, ast.Compare):
            left = evaluate(node.left)
            for operation, comparator in zip(node.ops, node.comparators):
                if type(operation) not in _COMPARE:
                    raise SyntaxError("Unsupported comparison")
                right = evaluate(comparator)
                if not _COMPARE[type(operation)](left, right):
                    return False
                left = right
            return True
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and not node.keywords:
            args = [evaluate(a) for a in node.args]
            if node.func.id in _BUILTINS:
                return _BUILTINS[node.func.id](*args)
            if env is not self.env:
                raise SyntaxError("User function calls in measurement-dependent print expressions are unsupported")
            return self._call_function(node.func.id, args)
        raise SyntaxError("Unsupported expression: " + type(node).__name__)

    def _call_function(self, name, args):
        function = self.env.get(name)
        if not isinstance(function, FunctionDef):
            raise NameError("Function '{}' is not defined".format(name))
        if len(args) != len(function.args):
            raise TypeError("Function '{}' expects {} arguments, received {}".format(name, len(function.args), len(args)))
        for parameter, value in zip(function.args, args):
            if parameter in self._quantum_names and isinstance(value, _QubitRef):
                continue
            self._check_variable(parameter)
        if self._call_depth >= MAX_CALL_DEPTH:
            raise RuntimeError("Function call depth limit exceeded")
        old_env = self.env
        self.env = dict(old_env, **dict(zip(function.args, args)))
        self._call_depth += 1
        try:
            for child in function.body:
                self._emit(child)
        except _Return as result:
            return result.value
        finally:
            self._call_depth -= 1
            self.env = old_env
        return None

    def _uses_classical(self, node):
        return any(isinstance(n, ast.Name) and
                   (n.id in self._classical_names or n.id == "result") for n in ast.walk(node))

    def _runtime_bit(self, node):
        if isinstance(node, ast.Name) and node.id in self.cbit_map:
            return self.cbit_map[node.id]
        if isinstance(node, ast.Subscript) and isinstance(node.value, ast.Name):
            base = node.value.id
            index = self._integer(self._eval_expr(node.slice), "Classical bit index")
            if base == "result" and base not in self._classical_names:
                if not 0 <= index < self.qc.num_clbits:
                    raise IndexError("Result bit index is out of range")
                return index
            return self._c("{}[{}]".format(base, index))
        raise SyntaxError("Measurement conditions require one classical bit")

    def _if(self, node):
        if not self._uses_classical(node.test):
            for child in node.body if self._eval_expr(node.test) else node.orelse:
                self._emit(child)
            return
        test = node.test
        if not (isinstance(test, ast.Compare) and len(test.ops) == 1 and
                isinstance(test.ops[0], (ast.Eq, ast.NotEq))):
            raise SyntaxError("Use 'if classical_bit == 0/1 then' for measurement feedback")
        left, right = test.left, test.comparators[0]
        if not self._uses_classical(left):
            left, right = right, left
        bit = self._runtime_bit(left)
        value = self._eval_expr(right)
        if value not in (0, 1):
            raise ValueError("Measurement conditions compare a bit with 0 or 1")
        if isinstance(test.ops[0], ast.NotEq):
            value = 1 - value
        self._dynamic_depth += 1
        try:
            with self.qc.if_test((self.qc.clbits[bit], int(value))) as otherwise:
                for child in node.body:
                    self._emit(child)
            if node.orelse:
                with otherwise:
                    for child in node.orelse:
                        self._emit(child)
        finally:
            self._dynamic_depth -= 1

    def _teleport(self, node):
        if self._dynamic_depth:
            raise SyntaxError("The teleport shorthand must be outside measurement conditionals")
        q1, q2, q3 = self._q(node.q1), self._q(node.q2), self._q(node.q3)
        if len({q1, q2, q3}) != 3:
            raise ValueError("Teleportation requires three distinct qubits")
        if self.qc.num_clbits + 2 > MAX_CBITS:
            raise ValueError("Teleportation exceeds the classical bit limit")
        # Named registers keep all memory bits visible in Aer counts and samples.
        bits = ClassicalRegister(2, "teleport_{}".format(self.qc.num_clbits))
        self.qc.add_register(bits)
        self.qc.h(q2)
        self.qc.cx(q2, q3)
        self.qc.cx(q1, q2)
        self.qc.h(q1)
        self.qc.measure(q1, bits[0])
        self.qc.measure(q2, bits[1])
        with self.qc.if_test((bits[1], 1)):
            self.qc.x(q3)
        with self.qc.if_test((bits[0], 1)):
            self.qc.z(q3)
        self.has_measurements = True

    def get_circuit(self):
        if self.qc is None:
            raise RuntimeError("Call compile() first")
        return self.qc

    def export_qasm(self):
        return qasm3.dumps(self.get_circuit())

    def run_simulation(self, shots=1, seed=None, draw=True):
        circuit = self.get_circuit()
        if isinstance(shots, bool) or not isinstance(shots, int) or shots < 1:
            raise ValueError("Shots must be a positive integer")
        if draw:
            print("[qsm] Quantum Circuit:")
            drawing = str(circuit.draw(output="text"))
            encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
            print(drawing.encode(encoding, errors="replace").decode(encoding))
        counts = {}
        if self.has_measurements:
            try:
                from qiskit_aer import AerSimulator
            except ImportError as exc:
                raise RuntimeError("Simulation requires Qiskit Aer; install qsm with pip install .") from exc
            backend = AerSimulator()
            executable = transpile(circuit, backend, seed_transpiler=seed)
            result = backend.run(executable, shots=shots, memory=True, seed_simulator=seed).result()
            if not result.success:
                raise RuntimeError("Simulation failed: " + str(result.status))
            counts = result.get_counts()
            sample = result.get_memory()[0].replace(" ", "")
            self.variables["result"] = {i: int(bit) for i, bit in enumerate(reversed(sample))}
        self.execute_deferred_prints()
        return counts

    def _measurement_env(self):
        if self.has_measurements and "result" not in self.variables:
            raise RuntimeError("Run the simulation before printing measurements")
        sample = self.variables.get("result", dict.fromkeys(range(self.qc.num_clbits), 0))
        values = {"result": sample}
        for name, index in self.cbit_map.items():
            if "[" in name:
                base, offset = name[:-1].split("[")
                # A declared result register has its own indices, like every other register.
                if base not in values or base == "result" and values[base] is sample:
                    values[base] = {}
                values[base][int(offset)] = sample[index]
            else:
                values[name] = sample[index]
        return values

    @staticmethod
    def _format_value(value):
        if isinstance(value, dict):
            bitstring = "".join(str(value[i]) for i in sorted(value, reverse=True))
            return "{} ({})".format(bitstring, int(bitstring, 2)) if bitstring else ""
        return str(value)

    def execute_deferred_prints(self):
        measurements = self._measurement_env()
        for args, captured in self.deferred_prints:
            env = dict(captured, **measurements)
            print("[qsm]", " ".join(self._format_value(self._eval_expr(arg, env)) for arg in args))


# Conventional spelling for new callers; retain the original public API.
QsmCompiler = qsmCompiler
