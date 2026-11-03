"""Line-oriented parser for the Lua-inspired QSM language."""

import ast
import keyword
import re


class QBitDecl(ast.AST):
    _fields = ("targets",)


class CRegDecl(ast.AST):
    _fields = ("targets",)


class Hadamard(ast.AST):
    _fields = ("target",)


class XGate(Hadamard):
    pass


class YGate(Hadamard):
    pass


class ZGate(Hadamard):
    pass


class SGate(Hadamard):
    pass


class TGate(Hadamard):
    pass


class CX(ast.AST):
    _fields = ("ctrl", "targ")


class SwapGate(ast.AST):
    _fields = ("q1", "q2")


class MCZGate(ast.AST):
    _fields = ("controls", "target")


class Measure(ast.AST):
    _fields = ("target", "classical_target")


class Teleport(ast.AST):
    _fields = ("q1", "q2", "q3")


class Gate(ast.AST):
    _fields = ("name", "params", "targets")


class FunctionDef(ast.AST):
    _fields = ("name", "args", "body")


class FunctionCall(ast.AST):
    _fields = ("name", "args")


# name: (number of angle parameters, number of qubits); None permits many qubits.
GATES = {
    **{name: (0, None) for name in
       ("h", "hadamard", "x", "y", "z", "s", "sdg", "t", "tdg",
        "sx", "sxdg", "id", "reset", "barrier")},
    **{name: (0, 2) for name in ("cx", "cy", "cz", "ch", "swap")},
    **{name: (0, 3) for name in ("ccx", "cswap", "teleport")},
    **{name: (1, None) for name in ("rx", "ry", "rz", "p")},
    "u": (3, None),
    **{name: (1, 2) for name in
       ("cp", "crx", "cry", "crz", "rxx", "ryy", "rzz")},
    "mcx": (0, None), "mcz": (0, None),
}

_KEYWORDS = set("qbit creg if then elseif else end for while do function return print true false nil and or not".split())


def _identifier(name):
    if not re.fullmatch(r"[A-Za-z_]\w*", name) or keyword.iskeyword(name) or name in _KEYWORDS:
        raise SyntaxError("Invalid or reserved identifier '{}'".format(name))
    return name

_EXPR_TOKENS = re.compile(
    r'''("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|\b(true|false|nil)\b|(~=|\^)'''
)


def parse_expression(source):
    """Translate Lua literals/operators outside strings, preserving precedence."""
    replacements = {"true": "True", "false": "False", "nil": "None",
                    "~=": "!=", "^": "**"}
    translated = _EXPR_TOKENS.sub(
        lambda m: m[1] if m[1] is not None else replacements[m[2] or m[3]],
        source.strip(),
    )
    return ast.parse(translated, mode="eval").body


def split_arguments(source):
    """Split commas outside quotes, parentheses and register indices."""
    parts, stack, start, quote, escaped = [], [], 0, None, False
    for i, char in enumerate(source):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
        elif char in "([":
            stack.append(char)
        elif char in ")]":
            if not stack or stack.pop() != {")": "(", "]": "["}[char]:
                raise SyntaxError("Unmatched bracket")
        elif char == "," and not stack:
            parts.append(source[start:i].strip())
            start = i + 1
    if quote or stack:
        raise SyntaxError("Unterminated string or bracket")
    parts.append(source[start:].strip())
    if any(not part for part in parts):
        raise SyntaxError("Expected an argument")
    return parts


def _strip_comments(source):
    """Keep strings and line numbers intact while removing both comment forms."""
    output, i, quote = [], 0, None
    while i < len(source):
        char = source[i]
        if quote:
            output.append(char)
            if char == "\\" and i + 1 < len(source):
                i += 1
                output.append(source[i])
            elif char == quote:
                quote = None
        elif char in "\"'":
            quote = char
            output.append(char)
        elif source.startswith("--[[", i):
            end = source.find("]]", i + 4)
            if end < 0:
                raise SyntaxError("Unterminated multiline comment",
                                  ("<qsm>", source.count("\n", 0, i) + 1, 1, None))
            end += 2
            if source.startswith("--", end):
                end += 2
            output.extend("\n" if c == "\n" else " " for c in source[i:end])
            i = end
            continue
        elif source.startswith("--", i):
            end = source.find("\n", i)
            i = len(source) if end < 0 else end
            continue
        else:
            output.append(char)
        i += 1
    return "".join(output)


class qsmParser:
    def parse(self, code, filename="<qsm>"):
        self.filename = filename
        self.original_lines = code.splitlines()
        try:
            self.lines = _strip_comments(code).splitlines()
        except SyntaxError as exc:
            exc.filename = filename
            raise
        self.pos = 0
        return self._block()

    def _error(self, message, line=None):
        line = self.pos + 1 if line is None else line
        text = self.original_lines[line - 1] if line <= len(self.original_lines) else ""
        return SyntaxError(message, (self.filename, line, 1, text))

    def _block(self, terminators=()):
        nodes = []
        while self.pos < len(self.lines):
            source = self.lines[self.pos].strip()
            if source == "end" or source == "else" or source.startswith("elseif "):
                if source.split()[0] in terminators:
                    return nodes
                raise self._error("Unexpected '{}'".format(source))
            if not source:
                self.pos += 1
                continue
            lineno = self.pos + 1
            self.pos += 1
            try:
                node = self._statement(source)
            except (SyntaxError, ValueError) as exc:
                if isinstance(exc, SyntaxError) and exc.filename == self.filename:
                    raise
                raise self._error(getattr(exc, "msg", str(exc)), lineno) from None
            for item in node if isinstance(node, list) else [node]:
                item.lineno = lineno
                item.col_offset = 0
                nodes.append(item)
        if terminators:
            raise self._error("Missing 'end' for block", len(self.lines) or 1)
        return nodes

    def _end(self):
        if self.pos >= len(self.lines) or self.lines[self.pos].strip() != "end":
            raise self._error("Expected 'end'")
        self.pos += 1

    def _if(self, condition):
        body = self._block(("else", "elseif", "end"))
        tail = self.lines[self.pos].strip()
        orelse = []
        if tail.startswith("elseif "):
            match = re.fullmatch(r"elseif\s+(.+)\s+then", tail)
            if not match:
                raise self._error("Expected 'elseif condition then'")
            line = self.pos + 1
            self.pos += 1
            branch = self._if(parse_expression(match[1]))
            branch.lineno = line
            orelse = [branch]
        else:
            if tail == "else":
                self.pos += 1
                orelse = self._block(("end",))
            self._end()
        return ast.If(test=condition, body=body, orelse=orelse)

    def _statement(self, source):
        match = re.fullmatch(r"function\s+([A-Za-z_]\w*)\s*\((.*)\)", source)
        if match:
            _identifier(match[1])
            args = split_arguments(match[2]) if match[2].strip() else []
            for arg in args:
                _identifier(arg)
            if len(set(args)) != len(args):
                raise SyntaxError("Duplicate function parameter")
            body = self._block(("end",))
            self._end()
            return FunctionDef(name=match[1], args=args, body=body)
        match = re.fullmatch(r"for\s+([A-Za-z_]\w*)\s*=\s*(.+)\s+do", source)
        if match:
            _identifier(match[1])
            bounds = split_arguments(match[2])
            if len(bounds) not in (2, 3):
                raise SyntaxError("Expected 'for name = start, stop[, step] do'")
            iterator = ast.Call(func=ast.Name(id="inclusive_range", ctx=ast.Load()),
                                args=[parse_expression(b) for b in bounds], keywords=[])
            body = self._block(("end",))
            self._end()
            return ast.For(target=ast.Name(id=match[1], ctx=ast.Store()),
                           iter=iterator, body=body, orelse=[])
        match = re.fullmatch(r"while\s+(.+)\s+do", source)
        if match:
            test = parse_expression(match[1])
            body = self._block(("end",))
            self._end()
            return ast.While(test=test, body=body, orelse=[])
        match = re.fullmatch(r"if\s+(.+)\s+then", source)
        if match:
            return self._if(parse_expression(match[1]))
        match = re.fullmatch(r"(qbit|creg)\s+(.+)", source)
        if match:
            targets = []
            for name in split_arguments(match[2]):
                decl = re.fullmatch(r"([A-Za-z_]\w*)(?:\[\s*([0-9]+)\s*\])?", name)
                if not decl:
                    raise SyntaxError("Expected a register name or name[positive integer]")
                _identifier(decl[1])
                if decl[2] is None:
                    targets.append(decl[1])
                else:
                    size = int(decl[2])
                    if not 1 <= size <= 128:
                        raise SyntaxError("Register size must be between 1 and 128")
                    targets.extend("{}[{}]".format(decl[1], i) for i in range(size))
            return (QBitDecl if match[1] == "qbit" else CRegDecl)(targets=targets)
        if source.startswith("measure "):
            parts = source[8:].split("->")
            if len(parts) > 2:
                raise SyntaxError("Expected 'measure qubits [-> classical bits]'")
            targets = split_arguments(parts[0])
            if len(parts) == 2:
                classical = split_arguments(parts[1])
                if len(classical) != len(targets):
                    raise SyntaxError("Measurement source and destination counts differ")
            else:
                classical = [None] * len(targets)
            return [Measure(target=q, classical_target=c) for q, c in zip(targets, classical)]
        if source == "print" or source.startswith("print ") or source.startswith("print("):
            text = source[5:].strip()
            if text.startswith("("):
                call = parse_expression("print" + text)
                if not (isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
                        and call.func.id == "print" and not call.keywords):
                    raise SyntaxError("Expected 'print(expressions)' without keyword arguments")
            else:
                call = ast.Call(func=ast.Name(id="print", ctx=ast.Load()),
                                args=[parse_expression(p) for p in split_arguments(text)] if text else [],
                                keywords=[])
            return ast.Expr(value=call)
        if source == "return" or source.startswith("return "):
            return ast.Return(value=parse_expression(source[7:]) if source != "return" else None)

        # A gate's parameter list may itself contain nested function calls.
        head = re.match(r"([A-Za-z_]\w*)", source)
        if head and head[1] in GATES and not source[head.end():].lstrip().startswith("="):
            name, rest = head[1], source[head.end():].strip()
            params = []
            if rest.startswith("("):
                depth, quote, escaped, end = 0, None, False, None
                for i, char in enumerate(rest):
                    if quote:
                        if escaped:
                            escaped = False
                        elif char == "\\":
                            escaped = True
                        elif char == quote:
                            quote = None
                    elif char in "\"'":
                        quote = char
                    elif char == "(":
                        depth += 1
                    elif char == ")":
                        depth -= 1
                        if depth == 0:
                            end = i
                            break
                if end is None:
                    raise SyntaxError("Unterminated gate parameters")
                params = [parse_expression(p) for p in split_arguments(rest[1:end])]
                rest = rest[end + 1:].strip()
            targets = split_arguments(rest) if rest else []
            param_count, target_count = GATES[name]
            if len(params) != param_count:
                raise SyntaxError("Gate '{}' requires {} angle parameter(s)".format(name, param_count))
            if target_count is not None and len(targets) != target_count:
                raise SyntaxError("Gate '{}' requires {} qubits".format(name, target_count))
            if not targets and name != "barrier":
                raise SyntaxError("Gate '{}' requires qubit targets".format(name))
            if name in ("mcx", "mcz") and len(targets) < 2:
                raise SyntaxError("Expected controls followed by a target")
            legacy_single = {"h": Hadamard, "hadamard": Hadamard, "x": XGate,
                             "y": YGate, "z": ZGate, "s": SGate, "t": TGate}
            if name in legacy_single:
                return [legacy_single[name](target=t) for t in targets]
            if name == "cx":
                return CX(ctrl=targets[0], targ=targets[1])
            if name == "swap":
                return SwapGate(q1=targets[0], q2=targets[1])
            if name == "teleport":
                return Teleport(q1=targets[0], q2=targets[1], q3=targets[2])
            if name == "mcz":
                return MCZGate(controls=", ".join(targets[:-1]), target=targets[-1])
            return Gate(name=name, params=params, targets=targets)
        # Python supplies syntax trees only; the compiler never executes Python code.
        assignment = re.fullmatch(r"([A-Za-z_]\w*)\s*=\s*(?!=)(.+)", source)
        if assignment:
            _identifier(assignment[1])
            return ast.Assign(targets=[ast.Name(id=assignment[1], ctx=ast.Store())],
                              value=parse_expression(assignment[2]))
        expression = parse_expression(source)
        if isinstance(expression, ast.Call) and isinstance(expression.func, ast.Name) and not expression.keywords:
            return FunctionCall(name=expression.func.id, args=expression.args)
        raise SyntaxError("Unknown or unsupported statement")
