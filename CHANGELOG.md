# Changelog

## 0.2.0 — 2026-11-03

### Language

- Correct expression precedence, numeric assignments, negative values, index
  expressions, boolean operations, and short-circuit evaluation.
- Reliable nested blocks, `elseif`, inclusive descending loops, and while loops.
- Function expression arguments, individual qubit arguments, local environments,
  argument validation, and return values.
- Preserve quoted commas and comment markers, support both multiline comment
  endings, and report source filenames and line numbers for compilation errors.
- Reject unsupported statements and unknown names explicitly.

### Quantum operations

- Add inverse phase gates, square-root X gates, rotations, controlled gates,
  two-qubit rotations, multi-controlled X, reset, and barriers.
- Support whole-register and inclusive-range operands for single-qubit gates and
  measurement.
- Correct multi-controlled Z using H–MCX–H.
- Compile measurement-dependent bit comparisons into runtime conditionals.
- Implement teleportation with measurements and conditional corrections.
- Correct classical-register offsets, implicit measurement allocation, and
  deferred print values.
- Repair Grover search, phase estimation, and teleportation examples; add a
  language-features example.

### Tools and packaging

- Add `--shots`, `--seed`, `--no-draw`, `--check`, `--qasm`, and `--version`.
- Export OpenQASM 3 using the supported Qiskit exporter.
- Handle UTF-8 source files and Windows circuit-diagram output.
- Install Qiskit Aer with QSM and reset execution state between compilations.
- Add a VS Code extension with highlighting, snippets, hover help, indentation,
  folding, run/check commands, and compilation diagnostics.
- Refresh installation instructions and the full language reference.
- Add Python and editor tests and Windows/Linux continuous integration.

### Compatibility notes

- Register declarations belong at the top level and must have unique names and
  positive literal sizes. Language names and constants are reserved.
- Unknown variables and invalid indices now raise errors instead of defaulting
  to zero or being ignored.
- Measurement feedback supports single-bit equality/inequality with 0 or 1.
  Runtime assignments, returns, printing, and measurement-dependent while loops
  remain unsupported; see `QSM_LANGUAGE.md` for details.
- The VS Code extension is distributed as a local VSIX package and has not been
  published to the Marketplace. Its UI has not been manually exercised.
