from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import numpy as np
from qiskit import QuantumCircuit
from qiskit.quantum_info import Operator

from qsm.compiler import qsmCompiler
from qsm.parser import GATES, qsmParser

ROOT = Path(__file__).resolve().parents[1]


def simulate(source, shots=32):
    compiler = qsmCompiler()
    compiler.compile(source)
    output = io.StringIO()
    with redirect_stdout(output):
        counts = compiler.run_simulation(shots=shots, seed=7, draw=False)
    return compiler, counts, output.getvalue()


class CoreLanguageTests(unittest.TestCase):
    def test_nested_blocks_do_not_skip_statements(self):
        compiler, counts, _ = simulate('''
qbit q[3]
creg answer[3]
function prepare(n)
    for i = 0, n-1 do
        if i % 2 == 0 then
            x q[i]
        else
            h q[i]
            h q[i]
        end -- nested block
        z q[i]
    end -- loop
end -- function
prepare(3)
measure q -> answer
''')
        self.assertEqual(counts, {"101": 32})
        self.assertEqual(compiler.qc.count_ops()["z"], 3)

    def test_expression_precedence_functions_and_negative_indices(self):
        _, counts, output = simulate('''
qbit q[3]
creg bits[3]
function offset(n)
    return (n + 1) * 2
end
index = offset(1) - 2
angle = -pi / 2
rx(angle * -2) q[index]
measure q -> bits
print bits[index-1+1], 2 + 3 * 4, (2 + 3) * 4, 2^3^2
''')
        self.assertEqual(counts, {"100": 32})
        self.assertIn("1 14 20 512", output)

    def test_descending_loops_and_elseif(self):
        _, counts, output = simulate('''
qbit q[3]
for i=2, 0, -1 do
    if i == 2 then
        x q[i]
    elseif i == 1 then
        h q[i]
        h q[i]
    else
        x q[i]
    end
    print i
end
measure q
''')
        self.assertEqual(counts, {"101": 32})
        self.assertEqual(output.splitlines(), ["[qsm] 2", "[qsm] 1", "[qsm] 0"])

    def test_while_assignments_boolean_literals_and_short_circuit(self):
        _, counts, output = simulate('''
qbit q[2]
i = 0
while i < 2 and true do
    x q[i]
    i = i + 1
end
if false or (i ~= 0 and not false) then
    print "true, ~= ^ -- literal", i
end
print false and missing, true or missing, nil
measure q
''')
        self.assertEqual(counts, {"11": 32})
        self.assertIn("true, ~= ^ -- literal 2", output)
        self.assertIn("False True None", output)

    def test_comments_strings_and_nested_call_commas(self):
        _, _, output = simulate('''
--[[ multi
line ]]
--[[ legacy ]]--
value = max(2, min(4, 3))
print "hello, --[[world]]--", value, "escaped \\\"--\\\"", "\\n"
''')
        self.assertIn('hello, --[[world]]-- 3 escaped "--"', output)

    def test_prints_capture_each_environment(self):
        _, _, output = simulate('''
value = 1
print value
value = 2
print value
function display(n)
    print n
end
display(value + 3)
''')
        self.assertEqual(output.splitlines(), ["[qsm] 1", "[qsm] 2", "[qsm] 5"])

    def test_qubit_function_arguments_and_local_variables(self):
        compiler, counts, _ = simulate('''
qbit q[2]
value = 7
function prepare(a, b, angle)
    value = 99
    ry(angle) a
    cx a, b
end
prepare(q[0], q[1], pi)
measure q
''')
        self.assertEqual(counts, {"11": 32})
        self.assertEqual(compiler.env["value"], 7)

    def test_qubit_parameter_can_shadow_a_global_register(self):
        _, counts, _ = simulate('''
qbit q[2]
function flip(q)
    x q
end
flip(q[1])
measure q
''')
        self.assertEqual(counts, {'10': 32})

    def test_recompile_clears_all_previous_state(self):
        compiler = qsmCompiler()
        compiler.compile('qbit a\nx a\nmeasure a\nprint result')
        compiler.compile('qbit b\nh b')
        self.assertEqual(compiler.qreg, ["b"])
        self.assertFalse(compiler.has_measurements)
        self.assertFalse(compiler.deferred_prints)
        self.assertEqual(compiler.qc.num_clbits, 0)

    def test_unknown_names_and_out_of_range_indices_fail(self):
        for source in ('qbit q[2]\nx q[missing]', 'qbit q[2]\nx q[2]',
                       'qbit q[2]\nx q[-1]', 'print missing',
                       'qbit q[2]\nx q[0..1000000000]'):
            with self.subTest(source=source), self.assertRaises(NameError):
                qsmCompiler().compile(source)

    def test_invalid_syntax_reports_original_line(self):
        for source, line in [('qbit q\n\n-- comment\nfrobnicate q', 4),
                             ('end', 1), ('qbit q\ncp(pi) q', 2),
                             ('if true then\nx q', 2)]:
            with self.subTest(source=source), self.assertRaises(SyntaxError) as error:
                qsmParser().parse(source, filename='bad.qsm')
            self.assertEqual(error.exception.lineno, line)
            self.assertEqual(error.exception.filename, 'bad.qsm')

    def test_invalid_programs_fail_explicitly(self):
        programs = ['qbit q[0]', 'qbit q[129]', 'qbit a, a', 'qbit a\ncreg a',
                    'qbit q[2]\nmeasure q -> answer', 'qbit q\nreturn 1',
                    'function f(a)\nend\nf()', 'for i=0, 1, 0 do\nend',
                    'qbit q[2]\nmcz q[0], q[0]', 'qbit q\nrx("pi") q',
                    'function f()\nqbit q\nend', 'qbit q\nq = 2',
                    'qbit q\nx q[0.5]']
        for source in programs:
            with self.subTest(source=source), self.assertRaises((SyntaxError, ValueError, NameError, TypeError)):
                qsmCompiler().compile(source)

    def test_loop_and_recursion_limits(self):
        with patch('qsm.compiler.MAX_ITERATIONS', 3), self.assertRaisesRegex(RuntimeError, 'iteration limit'):
            qsmCompiler().compile('while true do\nend')
        with patch('qsm.compiler.MAX_CALL_DEPTH', 3), self.assertRaisesRegex(RuntimeError, 'depth limit'):
            qsmCompiler().compile('function recurse()\nrecurse()\nend\nrecurse()')

    def test_python_execution_is_not_exposed(self):
        for source in ['import os', 'print __import__("os")', 'print (1).__class__',
                       'print [x for x in range(2)]']:
            with self.subTest(source=source), self.assertRaises((SyntaxError, NameError)):
                qsmCompiler().compile(source)


class QuantumTests(unittest.TestCase):
    def test_every_gate_matches_qiskit(self):
        for name, (nparams, nqubits) in GATES.items():
            if name in ('teleport', 'mcx', 'mcz'):
                continue
            with self.subTest(gate=name):
                nqubits = nqubits or 1
                params = [0.17 * (i + 1) for i in range(nparams)]
                text = name + ('(' + ', '.join(map(str, params)) + ')' if params else '')
                targets = ', '.join('q[{}]'.format(i) for i in range(nqubits))
                actual = qsmCompiler().compile('qbit q[{}]\n{} {}'.format(nqubits, text, targets))
                expected = QuantumCircuit(nqubits)
                getattr(expected, 'h' if name == 'hadamard' else name)(*params, *range(nqubits))
                if name in ('reset', 'barrier'):
                    self.assertEqual(actual, expected)
                else:
                    np.testing.assert_allclose(Operator(actual).data, Operator(expected).data, atol=1e-12)

    def test_multi_controlled_z_has_exact_phase_for_each_basis_state(self):
        for size in range(2, 6):
            with self.subTest(size=size):
                circuit = qsmCompiler().compile('qbit q[{0}]\nmcz q[0..{1}], q[{2}]'.format(size, size-2, size-1))
                expected = np.eye(2**size, dtype=complex)
                expected[-1, -1] = -1
                np.testing.assert_allclose(Operator(circuit).data, expected, atol=1e-12)

    def test_mcx_and_explicit_control_lists(self):
        _, counts, _ = simulate('qbit q[3]\nx q[0..1]\nmcx q[0], q[1], q[2]\nmeasure q')
        self.assertEqual(counts, {'111': 32})

    def test_separate_registers_use_their_actual_classical_offsets(self):
        _, _, output = simulate('''
qbit q[3]
creg first[1], result[2]
x q[0], q[2]
measure q[0] -> first[0]
measure q[1] -> result[0]
measure q[2] -> result[1]
print first, result, first[0], result[0], result[1]
''')
        self.assertIn('1 (1) 10 (2) 1 0 1', output)

    def test_scalar_register_and_default_measurement(self):
        _, counts, output = simulate('qbit a, b\ncreg output\nx a\nmeasure a -> output\nmeasure b\nprint output, result')
        self.assertEqual(counts, {'001': 32})
        self.assertIn('1 001 (1)', output)

    def test_unmeasured_classical_bits_start_at_zero(self):
        _, counts, output = simulate('creg bit, answer[2]\nprint bit, answer')
        self.assertEqual(counts, {})
        self.assertEqual(output.strip(), '[qsm] 0 00 (0)')

    def test_measurement_feedback_and_else(self):
        for condition in ('m[0] == 1', 'm[0] ~= 0', '1 == m[0]'):
            _, counts, _ = simulate('''
qbit q[2]
creg m[1], out[1]
h q[0]
measure q[0] -> m[0]
if CONDITION then
    x q[1]
else
    z q[1]
end
measure q[1] -> out[0]
'''.replace('CONDITION', condition), shots=64)
            self.assertEqual(set(counts), {'00', '11'})

    def test_unsupported_runtime_classical_work_fails(self):
        for body in ('value = 1', 'print "branch"', 'return 1'):
            with self.subTest(body=body), self.assertRaises(SyntaxError):
                qsmCompiler().compile('qbit q\ncreg bit\nmeasure q -> bit\nif bit == 1 then\n' + body + '\nend')

    def test_teleport_shorthand_preserves_arbitrary_states(self):
        for prepare, undo in [('x q[0]', 'x q[2]'), ('h q[0]', 'h q[2]'),
                              ('ry(pi/3) q[0]\nrz(pi/7) q[0]', 'rz(-pi/7) q[2]\nry(-pi/3) q[2]')]:
            _, counts, output = simulate('qbit q[3]\ncreg out\n' + prepare +
                                     '\nteleport q[0], q[1], q[2]\n' + undo +
                                     '\nmeasure q[2] -> out\nprint out', shots=64)
            self.assertEqual(output.strip(), '[qsm] 0')
            self.assertEqual(sum(counts.values()), 64)
            self.assertTrue(all(bits.replace(' ', '')[-1] == '0' for bits in counts))

    def test_shot_validation_and_seed(self):
        compiler = qsmCompiler()
        compiler.compile('qbit q\nh q\nmeasure q')
        first = compiler.run_simulation(shots=64, seed=42, draw=False)
        second = compiler.run_simulation(shots=64, seed=42, draw=False)
        self.assertEqual(first, second)
        for invalid in (0, -1, True, 1.5):
            with self.assertRaises(ValueError):
                compiler.run_simulation(shots=invalid, draw=False)

    def test_qasm3_export(self):
        compiler = qsmCompiler()
        compiler.compile('qbit q[3]\nmcz q[0..1], q[2]\nmeasure q')
        self.assertTrue(compiler.export_qasm().startswith('OPENQASM 3.0;'))
        compiler.compile('qbit q[3]\nteleport q[0], q[1], q[2]')
        self.assertIn('if (', compiler.export_qasm())

    def test_all_examples_compile_and_simulate(self):
        for path in (ROOT / 'examples').glob('*.qsm'):
            with self.subTest(example=path.name):
                _, counts, output = simulate(path.read_text(encoding='utf-8-sig'), shots=128)
                self.assertEqual(sum(counts.values()), 128)
                if path.name == '3-cubit_QFT.qsm':
                    self.assertEqual(counts, {'101': 128})
                elif path.name == 'quantum_phase_estimation.qsm':
                    self.assertEqual(counts, {'100': 128})
                elif path.name == 'grovers_algorithm.qsm':
                    self.assertGreater(counts.get('1010', 0), 110)
                elif path.name == 'quantum_teleportation.qsm':
                    self.assertTrue(all(bits[0] == '0' for bits in counts))
                    self.assertIn('expected 0): 0', output)
                elif path.name == 'language_features.qsm':
                    self.assertEqual(counts, {'011': 128})
                elif path.name == 'bell_state.qsm':
                    self.assertEqual(set(counts), {'00', '11'})


class CLITests(unittest.TestCase):
    def cli(self, *args):
        return subprocess.run([sys.executable, '-m', 'qsm', *args], cwd=ROOT,
                              capture_output=True, text=True, encoding='utf-8')

    def test_help_and_invalid_flags(self):
        self.assertEqual(self.cli('--help').returncode, 0)
        result = self.cli('examples/bell_state.qsm', '--unknown')
        self.assertEqual(result.returncode, 2)
        self.assertNotIn('not found', result.stderr)

    def test_release_versions_are_consistent(self):
        from qsm import __version__
        manifest = json.loads((ROOT / 'editors/vscode/package.json').read_text())
        lock = json.loads((ROOT / 'editors/vscode/package-lock.json').read_text())
        self.assertEqual(manifest['version'], __version__)
        self.assertEqual(lock['version'], __version__)
        self.assertEqual(lock['packages']['']['version'], __version__)
        result = self.cli('--version')
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.strip(), 'qsm ' + __version__)

    def test_compile_check_does_not_simulate(self):
        result = self.cli('examples/bell_state.qsm', '--check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Valid:', result.stdout)
        self.assertNotIn('Bell state result', result.stdout)

    def test_run_shots_and_export(self):
        result = self.cli('examples/bell_state.qsm', '--shots', '8', '--seed', '42', '--no-draw')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Counts:', result.stdout)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'circuit.qasm'
            result = self.cli('examples/bell_state.qsm', '--qasm', str(output))
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(output.read_text().startswith('OPENQASM 3.0;'))

    def test_circuit_diagram_and_utf8_output(self):
        result = self.cli('examples/bell_state.qsm', '--seed', '42')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('\u250c', result.stdout)
        self.assertNotIn('limited charset', result.stderr)

    def test_source_errors_have_filename_and_line(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'bad.qsm'
            source.write_text('qbit q\nx missing', encoding='utf-8')
            result = self.cli(str(source))
            self.assertEqual(result.returncode, 1)
            self.assertIn(str(source) + ':2:', result.stderr)
            self.assertNotIn('Traceback', result.stderr)


class EditorIntegrationTests(unittest.TestCase):
    def test_hover_help_and_grammar_cover_all_supported_gates(self):
        root = ROOT / 'editors' / 'vscode'
        help_text = json.loads((root / 'gate-help.json').read_text())
        self.assertTrue(set(GATES) <= set(help_text))
        grammar = json.loads((root / 'syntaxes/qsm.tmLanguage.json').read_text())
        rule = next(p['match'] for p in grammar['patterns'] if p.get('name') == 'support.function.quantum.qsm')
        for gate in GATES:
            self.assertIsNotNone(re.fullmatch(rule, gate), gate)

    def test_snippet_defaults_parse_as_valid_qsm(self):
        snippets = json.loads((ROOT / 'editors/vscode/snippets/qsm.json').read_text())
        for name, snippet in snippets.items():
            with self.subTest(snippet=name):
                source = '\n'.join(snippet['body'])
                source = re.sub(r'\$\{\d+:([^}]+)\}|\$\{\d+\}|\$\d+',
                                lambda match: match[1] or '', source)
                qsmParser().parse(source)

    def test_invalid_prints_reserved_names_and_comment_locations(self):
        for source in ['print(value=1)', 'print()(1)', 'qbit true',
                       'function f(end)\nend', 'qbit pi', 'qbit rx']:
            with self.subTest(source=source), self.assertRaises((SyntaxError, ValueError)):
                qsmCompiler().compile(source)
        with self.assertRaises(SyntaxError) as error:
            qsmParser().parse('qbit q\n--[[ unfinished', filename='comment.qsm')
        self.assertEqual(error.exception.filename, 'comment.qsm')
        self.assertEqual(error.exception.lineno, 2)


if __name__ == '__main__':
    unittest.main()
