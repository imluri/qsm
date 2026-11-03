# qsm/__main__.py
"""
qsm CLI entry point

Allows running qsm scripts from the command line, similar to python or lua.
"""

import argparse
from pathlib import Path
import sys

from qsm import __version__
from qsm.compiler import qsmCompiler


def main(argv=None):
    # Windows redirects otherwise default to a legacy code page, which cannot
    # represent Qiskit's circuit diagrams or arbitrary UTF-8 program output.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(
        description='QSM Quantum Programming Language',
        prog='qsm'
    )
    parser.add_argument('script', help='QSM source file to compile and run')
    parser.add_argument('--debug', action='store_true', help='Show debug output and tracebacks')
    parser.add_argument('--shots', type=int, default=1, help='Number of simulation shots (default: 1)')
    parser.add_argument('--seed', type=int, help='Seed for reproducible simulation')
    parser.add_argument('--no-draw', action='store_true', help='Hide the circuit diagram')
    output = parser.add_mutually_exclusive_group()
    output.add_argument('--check', action='store_true', help='Validate without simulation')
    output.add_argument('--qasm', metavar='PATH', help='Export OpenQASM 3 without simulation')
    parser.add_argument('--version', action='version', version='qsm ' + __version__)
    args = parser.parse_args(argv)
    if args.shots < 1:
        parser.error('--shots must be a positive integer')
    if args.seed is not None and args.seed < 0:
        parser.error('--seed must be non-negative')
    try:
        path = Path(args.script)
        code = path.read_text(encoding='utf-8-sig')
        compiler = qsmCompiler(debug=args.debug)
        compiler.compile(code, filename=str(path))
        if args.check:
            print('[qsm] Valid: ' + str(path))
        elif args.qasm:
            Path(args.qasm).write_text(compiler.export_qasm(), encoding='utf-8')
            print('[qsm] OpenQASM 3 written to ' + args.qasm)
        else:
            counts = compiler.run_simulation(shots=args.shots, seed=args.seed, draw=not args.no_draw)
            if args.shots > 1 and counts:
                print('[qsm] Counts:', counts)
        return 0
    except Exception as exc:
        if args.debug:
            raise
        location = getattr(exc, 'qsm_location', None)
        if isinstance(exc, SyntaxError) and exc.filename:
            location = '{}:{}'.format(exc.filename, exc.lineno)
        print('{}: {}'.format(location or args.script, getattr(exc, 'msg', str(exc))), file=sys.stderr)
        return 1

if __name__ == "__main__":
    raise SystemExit(main())
