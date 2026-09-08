"""AST -> instrumented AST.

The heart of the Python frontend.  Each rewrite rule here corresponds to a row
in docs/05-python-execution-strategy.md section K.4, and to a probe in
``runtime/probe.py``.

Two rules govern every rewrite:

1. **Semantics are preserved exactly.**  Operand evaluation order, short-circuit
   behaviour, single evaluation of augmented-assignment targets, and generator
   laziness all survive.  ``tests/unit/test_semantic_preservation.py`` executes
   every fixture twice -- native and instrumented -- and compares output,
   return value and exception.  That test is a merge gate.

2. **When a safe rewrite is not obvious, we decline.**  The construct is left
   alone, an ``INSTRUMENTATION_SKIPPED`` event is emitted at its line, and the
   capability report names it.  Reduced detail is acceptable; a confidently
   wrong picture is not.

Locations are copied from the original nodes, so the compiled code object
carries the *original* line numbers and tracebacks stay meaningful.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from typing import Any

GRANULARITIES = ("minimal", "standard", "verbose")

_CMP_OPS: dict[type, str] = {
    ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">=",
    ast.Eq: "==", ast.NotEq: "!=", ast.Is: "is", ast.IsNot: "is not",
    ast.In: "in", ast.NotIn: "not in",
}
_BIN_OPS: dict[type, str] = {
    ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/",
    ast.FloorDiv: "//", ast.Mod: "%", ast.Pow: "**",
    ast.LShift: "<<", ast.RShift: ">>", ast.BitOr: "|",
    ast.BitAnd: "&", ast.BitXor: "^", ast.MatMult: "@",
}


@dataclass
class Skip:
    line: int
    col: int
    construct: str
    reason: str


@dataclass
class InstrumentResult:
    tree: ast.Module
    skips: list[Skip] = field(default_factory=list)
    loop_ids: dict[str, int] = field(default_factory=dict)   # loop_id -> line
    func_ids: dict[str, str] = field(default_factory=dict)   # func_id -> name


def loop_id_for(node: ast.stmt) -> str:
    return f"L{node.lineno}c{node.col_offset}"


def func_id_for(node: ast.AST, name: str) -> str:
    return f"F{name}@{getattr(node, 'lineno', 0)}"


class Instrumenter(ast.NodeTransformer):
    """Rewrites a parsed module so that its execution emits events."""

    def __init__(self, granularity: str = "standard") -> None:
        if granularity not in GRANULARITIES:
            raise ValueError(f"unknown granularity {granularity!r}")
        self.granularity = granularity
        self.verbose = granularity == "verbose"
        self.standard = granularity in ("standard", "verbose")
        self.skips: list[Skip] = []
        self.loop_ids: dict[str, int] = {}
        self.func_ids: dict[str, str] = {}
        self._func_stack: list[str] = []
        self._loop_stack: list[str] = []

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def run(self, tree: ast.Module) -> InstrumentResult:
        tree.body = self._body(tree.body, is_module=True)
        ast.fix_missing_locations(tree)
        return InstrumentResult(tree, self.skips, self.loop_ids, self.func_ids)

    # ------------------------------------------------------------------
    # node builders
    # ------------------------------------------------------------------
    def _call(self, fn: str, args: list[ast.expr], src: ast.AST,
              keywords: list[ast.keyword] | None = None) -> ast.Call:
        node = ast.Call(
            func=ast.Name(id=fn, ctx=ast.Load()),
            args=args,
            keywords=keywords or [],
        )
        return ast.copy_location(_fill(node, src), src)

    def _stmt(self, fn: str, args: list[ast.expr], src: ast.AST) -> ast.Expr:
        return ast.copy_location(ast.Expr(value=self._call(fn, args, src)), src)

    def _k(self, value: Any, src: ast.AST) -> ast.Constant:
        return ast.copy_location(ast.Constant(value=value), src)

    def _skip(self, node: ast.AST, construct: str, reason: str) -> None:
        self.skips.append(
            Skip(getattr(node, "lineno", 0), getattr(node, "col_offset", 0), construct, reason)
        )

    # ------------------------------------------------------------------
    # statement bodies
    # ------------------------------------------------------------------
    def _body(self, stmts: list[ast.stmt], is_module: bool = False,
              is_function: bool = False) -> list[ast.stmt]:
        out: list[ast.stmt] = []
        for i, stmt in enumerate(stmts):
            # Keep a leading docstring in place -- moving it would change __doc__.
            if i == 0 and _is_docstring(stmt) and (is_module or is_function):
                out.append(stmt)
                continue
            mark = len(self.skips)
            transformed = self.visit(stmt)
            pre: list[ast.stmt] = []
            if not isinstance(stmt, (ast.Global, ast.Nonlocal)):
                pre.append(self._stmt("_as_line", [self._k(stmt.lineno, stmt)], stmt))
            # Any construct declined while transforming this statement is
            # reported at its own line.  Nested statements report again; the
            # probe de-duplicates by (line, construct) at run time.
            for s in self.skips[mark:]:
                pre.append(
                    self._stmt(
                        "_as_skip",
                        [self._k(s.reason, stmt), self._k(s.construct, stmt),
                         self._k(s.line, stmt)],
                        stmt,
                    )
                )
            out.extend(pre)
            if transformed is None:
                continue
            if isinstance(transformed, list):
                out.extend(transformed)
            else:
                out.append(transformed)
        if stmts and not out:
            out.append(ast.copy_location(ast.Pass(), stmts[0]))
        return out

    # ------------------------------------------------------------------
    # assignment
    # ------------------------------------------------------------------
    def visit_Assign(self, node: ast.Assign) -> Any:
        node.value = self.visit(node.value)
        if len(node.targets) == 1:
            target = node.targets[0]
            if isinstance(target, ast.Name):
                node.value = self._call(
                    "_as_store",
                    [self._k(target.id, node), node.value, self._k(node.lineno, node)],
                    node,
                )
                return node
            if isinstance(target, ast.Subscript):
                container = self.visit(target.value)
                index = self._index_expr(target)
                if index is not None:
                    # (value, container, index) mirrors CPython's evaluation order
                    return self._stmt(
                        "_as_sub_set",
                        [node.value, container, index, self._k(node.lineno, node)],
                        node,
                    )
            if isinstance(target, ast.Attribute):
                obj = self.visit(target.value)
                return self._stmt(
                    "_as_attr_set",
                    [node.value, obj, self._k(target.attr, node), self._k(node.lineno, node)],
                    node,
                )
        if len(node.targets) == 1:
            decomposed = self._decompose_tuple_assign(node, node.targets[0])
            if decomposed is not None:
                return decomposed
        # Starred / nested / multiple targets: keep the statement and read the
        # bound values back from the frame afterwards.  Exact values, coarser detail.
        names = _target_names(node.targets)
        if names:
            return [node, self._sync(names, node)]
        return node

    def _decompose_tuple_assign(self, node: ast.Assign, target: ast.expr):
        """``a[i], a[j] = a[j], a[i]`` -> one probe per element.

        Without this the element writes are invisible: a tuple target is not a
        Subscript, so the whole statement would fall through to a frame sync,
        which sees only that ``a`` still points at the same list.  Swaps -- the
        single most important operation in a sorting visualization -- would
        vanish, and no amount of lifting could recover them.

        Only flat targets of Name/Subscript/Attribute qualify; starred and
        nested targets keep the frame-sync path.
        """
        if not isinstance(target, (ast.Tuple, ast.List)):
            return None
        elements = target.elts
        if not elements or not all(
            isinstance(e, (ast.Name, ast.Subscript, ast.Attribute)) for e in elements
        ):
            return None
        if not any(isinstance(e, (ast.Subscript, ast.Attribute)) for e in elements):
            return None   # all-Name targets are already handled well by _as_sync

        tmp = f"_as_u{node.lineno}_{node.col_offset}"
        out: list[ast.stmt] = [
            ast.copy_location(
                ast.Assign(
                    targets=[ast.copy_location(ast.Name(id=tmp, ctx=ast.Store()), node)],
                    value=self._call(
                        "_as_unpack",
                        [node.value, self._k(len(elements), node),
                         self._k(node.lineno, node)],
                        node,
                    ),
                ),
                node,
            )
        ]
        for i, element in enumerate(elements):
            item = ast.copy_location(
                ast.Subscript(
                    value=ast.copy_location(ast.Name(id=tmp, ctx=ast.Load()), node),
                    slice=self._k(i, node),
                    ctx=ast.Load(),
                ),
                node,
            )
            if isinstance(element, ast.Name):
                out.append(
                    ast.copy_location(
                        ast.Assign(
                            targets=[ast.copy_location(
                                ast.Name(id=element.id, ctx=ast.Store()), node)],
                            value=self._call(
                                "_as_store",
                                [self._k(element.id, node), item,
                                 self._k(node.lineno, node)],
                                node,
                            ),
                        ),
                        node,
                    )
                )
            elif isinstance(element, ast.Subscript):
                index = self._index_expr(element)
                if index is None:
                    return None
                out.append(
                    self._stmt(
                        "_as_sub_set",
                        [item, self.visit(element.value), index,
                         self._k(node.lineno, node)],
                        node,
                    )
                )
            else:
                out.append(
                    self._stmt(
                        "_as_attr_set",
                        [item, self.visit(element.value),
                         self._k(element.attr, node), self._k(node.lineno, node)],
                        node,
                    )
                )
        return out

    def visit_AnnAssign(self, node: ast.AnnAssign) -> Any:
        if node.value is None:
            return node
        node.value = self.visit(node.value)
        if isinstance(node.target, ast.Name):
            node.value = self._call(
                "_as_store",
                [self._k(node.target.id, node), node.value, self._k(node.lineno, node)],
                node,
            )
        return node

    def visit_AugAssign(self, node: ast.AugAssign) -> Any:
        op = _BIN_OPS.get(type(node.op))
        node.value = self.visit(node.value)
        if op is None:
            return node
        target = node.target
        if isinstance(target, ast.Name):
            inplace = self._call(
                "_as_inplace",
                [
                    self._k(op, node),
                    ast.copy_location(ast.Name(id=target.id, ctx=ast.Load()), node),
                    node.value,
                    self._k(node.lineno, node),
                ],
                node,
            )
            stored = self._call(
                "_as_store",
                [self._k(target.id, node), inplace, self._k(node.lineno, node)],
                node,
            )
            return ast.copy_location(
                ast.Assign(
                    targets=[ast.copy_location(ast.Name(id=target.id, ctx=ast.Store()), node)],
                    value=stored,
                ),
                node,
            )
        if isinstance(target, ast.Subscript):
            container = self.visit(target.value)
            index = self._index_expr(target)
            if index is not None:
                # single evaluation of container and index
                return self._stmt(
                    "_as_sub_aug",
                    [self._k(op, node), container, index, node.value,
                     self._k(node.lineno, node)],
                    node,
                )
        if isinstance(target, ast.Attribute):
            obj = self.visit(target.value)
            return self._stmt(
                "_as_attr_aug",
                [self._k(op, node), obj, self._k(target.attr, node), node.value,
                 self._k(node.lineno, node)],
                node,
            )
        self._skip(node, "augmented assignment",
                   "target not modelled; values synced after the statement")
        names = _target_names([target])
        return [node, self._sync(names, node)] if names else node

    def visit_Delete(self, node: ast.Delete) -> Any:
        out: list[ast.stmt] = []
        keep: list[ast.expr] = []
        for target in node.targets:
            if isinstance(target, ast.Name):
                out.append(
                    self._stmt(
                        "_as_del_name",
                        [self._k(target.id, node), self._k(node.lineno, node)],
                        node,
                    )
                )
                keep.append(target)
            elif isinstance(target, ast.Subscript):
                container = self.visit(target.value)
                index = self._index_expr(target)
                if index is not None:
                    out.append(
                        self._stmt(
                            "_as_sub_del",
                            [container, index, self._k(node.lineno, node)],
                            node,
                        )
                    )
                else:
                    keep.append(target)
            else:
                keep.append(target)
        if keep:
            node.targets = keep
            out.append(node)
        return out

    def _sync(self, names: list[str], src: ast.AST) -> ast.Expr:
        tup = ast.copy_location(
            ast.Tuple(elts=[self._k(n, src) for n in names], ctx=ast.Load()), src
        )
        return self._stmt("_as_sync", [tup, self._k(src.lineno, src)], src)  # type: ignore[attr-defined]

    # ------------------------------------------------------------------
    # control flow
    # ------------------------------------------------------------------
    def visit_If(self, node: ast.If) -> Any:
        src = _src(node.test)
        node.test = self._call(
            "_as_cond",
            [
                self.visit(node.test),
                self._k("if", node),
                self._k(node.lineno, node),
                self._k(src, node),
            ],
            node,
        )
        body = self._body(node.body)
        node.body = [self._stmt("_as_branch", [self._k("then", node), self._k(node.lineno, node)], node)] + body
        if node.orelse:
            orelse = self._body(node.orelse)
            node.orelse = [self._stmt("_as_branch", [self._k("else", node), self._k(node.lineno, node)], node)] + orelse
        return node

    def visit_While(self, node: ast.While) -> Any:
        lid = loop_id_for(node)
        self.loop_ids[lid] = node.lineno
        src = _src(node.test)
        node.test = self._call(
            "_as_cond",
            [
                self.visit(node.test),
                self._k("while", node),
                self._k(node.lineno, node),
                self._k(src, node),
            ],
            node,
        )
        self._loop_stack.append(lid)
        body = self._body(node.body)
        node.body = [self._stmt("_as_loop_iter", [self._k(lid, node), self._k(node.lineno, node)], node)] + body
        node.orelse = self._body(node.orelse) if node.orelse else []
        self._loop_stack.pop()
        return self._wrap_loop(node, lid, "while")

    def visit_For(self, node: ast.For) -> Any:
        lid = loop_id_for(node)
        self.loop_ids[lid] = node.lineno
        var = node.target.id if isinstance(node.target, ast.Name) else ""
        node.iter = self._call(
            "_as_iter",
            [
                self._k(lid, node),
                self.visit(node.iter),
                self._k(node.lineno, node),
                self._k(var, node),
            ],
            node,
        )
        self._loop_stack.append(lid)
        body = self._body(node.body)
        # The loop variable is already bound by `for` when this runs, so a
        # _as_store probe would see old == new.  _as_sync compares against the
        # recorder's shadow: CREATED on the first iteration, a real old -> new
        # transition afterwards.
        capture = self._sync(_target_names([node.target]), node)
        node.body = [capture] + body
        node.orelse = self._body(node.orelse) if node.orelse else []
        self._loop_stack.pop()
        return self._wrap_loop(node, lid, "for")

    def _wrap_loop(self, node: ast.stmt, lid: str, kind: str) -> list[ast.stmt]:
        """Bracket a loop with enter/exit probes.

        ``_as_loop_exit`` goes in a ``finally`` so that break, return-from-loop
        and exceptions all produce a correct ``LOOP_FINISHED``.
        """
        enter = self._stmt(
            "_as_loop_enter",
            [self._k(lid, node), self._k(kind, node), self._k(node.lineno, node)],
            node,
        )
        exit_stmt = self._stmt(
            "_as_loop_exit", [self._k(lid, node), self._k(node.lineno, node)], node
        )
        wrapper = ast.copy_location(
            ast.Try(body=[node], handlers=[], orelse=[], finalbody=[exit_stmt]),
            node,
        )
        return [enter, wrapper]

    def visit_Break(self, node: ast.Break) -> Any:
        if not self._loop_stack:
            return node
        return [
            self._stmt(
                "_as_loop_break",
                [self._k(self._loop_stack[-1], node), self._k(node.lineno, node)],
                node,
            ),
            node,
        ]

    def visit_Try(self, node: ast.Try) -> Any:
        node.body = self._body(node.body)
        for handler in node.handlers:
            probe: ast.stmt
            if handler.name:
                probe = self._stmt(
                    "_as_handle",
                    [
                        ast.copy_location(ast.Name(id=handler.name, ctx=ast.Load()), handler),
                        self._k(handler.lineno, handler),
                    ],
                    handler,
                )
            else:
                probe = self._stmt(
                    "_as_handled",
                    [
                        self._k(_exc_name(handler.type), handler),
                        self._k(handler.lineno, handler),
                    ],
                    handler,
                )
            handler.body = [probe] + self._body(handler.body)
        node.orelse = self._body(node.orelse) if node.orelse else []
        node.finalbody = self._body(node.finalbody) if node.finalbody else []
        return node

    # Python 3.11+ exception groups share the Try shape.
    visit_TryStar = visit_Try

    def visit_Raise(self, node: ast.Raise) -> Any:
        if node.exc is not None:
            node.exc = self._call(
                "_as_raise",
                [self.visit(node.exc), self._k(node.lineno, node)],
                node,
            )
        return node

    def visit_With(self, node: ast.With) -> Any:
        self._skip(node, "with statement", "context manager enter/exit are not traced")
        for item in node.items:
            item.context_expr = self.visit(item.context_expr)
        node.body = self._body(node.body)
        return node

    def visit_Match(self, node: Any) -> Any:  # pragma: no cover - 3.10+ syntax
        self._skip(node, "match statement", "match is traced at statement level only")
        node.subject = self.visit(node.subject)
        for case in node.cases:
            case.body = self._body(case.body)
        return node

    # ------------------------------------------------------------------
    # functions and classes
    # ------------------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> Any:
        fid = func_id_for(node, node.name)
        self.func_ids[fid] = node.name

        if _contains_yield(node):
            # Generators suspend and resume, so a try/finally frame bracket would
            # corrupt the frame stack -- and with no frame of their own, their
            # variable events would be attributed to whoever resumed them.  Line
            # probes only: exactly the PARTIAL level the capability matrix states.
            self._skip(node, "generator function",
                       "generator bodies are traced at statement level only")
            node.body = self._lines_only(node.body)
            return node

        self._func_stack.append(fid)
        body = self._body(node.body, is_function=True)
        self._func_stack.pop()

        args_dict = self._args_dict(node.args, node)
        enter = self._stmt(
            "_as_enter",
            [
                self._k(node.name, node),
                self._k(fid, node),
                args_dict,
                self._k(node.lineno, node),
            ],
            node,
        )
        exit_stmt = self._stmt(
            "_as_exit", [self._k(fid, node), self._k(node.lineno, node)], node
        )
        wrapper = ast.copy_location(
            ast.Try(body=body or [ast.copy_location(ast.Pass(), node)],
                    handlers=[], orelse=[], finalbody=[exit_stmt]),
            node,
        )
        prefix: list[ast.stmt] = []
        if node.body and _is_docstring(node.body[0]):
            prefix.append(node.body[0])
        node.body = prefix + [enter, wrapper]
        return node

    def visit_AsyncFunctionDef(self, node: Any) -> Any:
        self._skip(node, "async function", "async execution is not modelled by the event engine")
        return node

    def visit_ClassDef(self, node: ast.ClassDef) -> Any:
        node.body = self._body(node.body, is_function=True)
        return node

    def visit_Return(self, node: ast.Return) -> Any:
        value = self.visit(node.value) if node.value is not None else None
        if self._func_stack and self._func_stack[-1]:
            fid = self._func_stack[-1]
            node.value = self._call(
                "_as_return",
                [
                    value if value is not None else self._k(None, node),
                    self._k(fid, node),
                    self._k(node.lineno, node),
                ],
                node,
            )
        else:
            node.value = value
        return node

    def _args_dict(self, args: ast.arguments, src: ast.AST) -> ast.Dict:
        keys: list[ast.expr] = []
        values: list[ast.expr] = []
        for a in list(getattr(args, "posonlyargs", [])) + list(args.args) + list(args.kwonlyargs):
            keys.append(self._k(a.arg, src))
            values.append(ast.copy_location(ast.Name(id=a.arg, ctx=ast.Load()), src))
        for extra in (args.vararg, args.kwarg):
            if extra is not None:
                keys.append(self._k(extra.arg, src))
                values.append(ast.copy_location(ast.Name(id=extra.arg, ctx=ast.Load()), src))
        return ast.copy_location(ast.Dict(keys=keys, values=values), src)

    def _lines_only(self, stmts: list[ast.stmt]) -> list[ast.stmt]:
        """Insert line probes and nothing else, recursing into nested bodies."""
        out: list[ast.stmt] = []
        for i, stmt in enumerate(stmts):
            if i == 0 and _is_docstring(stmt):
                out.append(stmt)
                continue
            if not isinstance(stmt, (ast.Global, ast.Nonlocal)):
                out.append(self._stmt("_as_line", [self._k(stmt.lineno, stmt)], stmt))
            for attr in ("body", "orelse", "finalbody"):
                nested = getattr(stmt, attr, None)
                if isinstance(nested, list) and nested and isinstance(nested[0], ast.stmt):
                    setattr(stmt, attr, self._lines_only(nested))
            for handler in getattr(stmt, "handlers", []) or []:
                handler.body = self._lines_only(handler.body)
            out.append(stmt)
        return out

    # ------------------------------------------------------------------
    # expressions
    # ------------------------------------------------------------------
    def visit_Subscript(self, node: ast.Subscript) -> Any:
        if not isinstance(node.ctx, ast.Load) or not self.standard:
            return self.generic_visit(node)
        container = self.visit(node.value)
        index = self._index_expr(node)
        if index is None:
            node.value = container
            return node
        return self._call(
            "_as_sub_get", [container, index, self._k(node.lineno, node)], node
        )

    def _index_expr(self, sub: ast.Subscript) -> ast.expr | None:
        """Turn a subscript's index into a plain expression, or ``None``.

        ``ast.Slice`` is only valid inside a ``Subscript``, so a slice is
        rebuilt as an explicit ``slice(...)`` call -- ``a[slice(1,5)]`` is
        exactly ``a[1:5]``.  Anything else (e.g. multi-dimensional tuples) is
        declined.
        """
        s = sub.slice
        if isinstance(s, ast.Slice):
            parts = [
                self.visit(s.lower) if s.lower is not None else self._k(None, sub),
                self.visit(s.upper) if s.upper is not None else self._k(None, sub),
                self.visit(s.step) if s.step is not None else self._k(None, sub),
            ]
            return self._call("slice", parts, sub)
        if isinstance(s, ast.Tuple):
            return None
        return self.visit(s)

    def visit_Attribute(self, node: ast.Attribute) -> Any:
        if not isinstance(node.ctx, ast.Load) or not self.verbose:
            return self.generic_visit(node)
        obj = self.visit(node.value)
        return self._call(
            "_as_attr_get", [obj, self._k(node.attr, node), self._k(node.lineno, node)], node
        )

    def visit_Call(self, node: ast.Call) -> Any:
        func = node.func
        if self.standard and isinstance(func, ast.Attribute) and isinstance(func.ctx, ast.Load):
            obj = self.visit(func.value)
            args = [self.visit(a) for a in node.args]
            keywords = [
                ast.keyword(arg=k.arg, value=self.visit(k.value)) for k in node.keywords
            ]
            call = ast.Call(
                func=ast.Name(id="_as_method", ctx=ast.Load()),
                args=[obj, self._k(func.attr, node), self._k(node.lineno, node)] + args,
                keywords=keywords,
            )
            return ast.copy_location(_fill(call, node), node)
        return self.generic_visit(node)

    def visit_Compare(self, node: ast.Compare) -> Any:
        if not self.standard or len(node.ops) != 1:
            # Chained comparisons short-circuit; leave the chain intact.
            return self.generic_visit(node)
        op = _CMP_OPS.get(type(node.ops[0]))
        if op is None:
            return self.generic_visit(node)
        left = self.visit(node.left)
        right = self.visit(node.comparators[0])
        return self._call(
            "_as_compare",
            [self._k(op, node), left, right, self._k(node.lineno, node)],
            node,
        )

    def visit_BinOp(self, node: ast.BinOp) -> Any:
        if not self.verbose:
            return self.generic_visit(node)
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            return self.generic_visit(node)
        left = self.visit(node.left)
        right = self.visit(node.right)
        return self._call(
            "_as_binop",
            [self._k(op, node), left, right, self._k(node.lineno, node)],
            node,
        )

    def visit_Name(self, node: ast.Name) -> Any:
        if not self.verbose or not isinstance(node.ctx, ast.Load):
            return node
        if node.id.startswith("_as_"):
            return node
        return self._call(
            "_as_load",
            [self._k(node.id, node), node, self._k(node.lineno, node)],
            node,
        )

    # Constructs with their own scope: descend no further.
    def visit_Lambda(self, node: ast.Lambda) -> Any:
        self._skip(node, "lambda", "lambda bodies are not instrumented")
        return node

    def visit_ListComp(self, node: ast.ListComp) -> Any:
        return self._comprehension(node, "list comprehension")

    def visit_SetComp(self, node: ast.SetComp) -> Any:
        return self._comprehension(node, "set comprehension")

    def visit_DictComp(self, node: ast.DictComp) -> Any:
        return self._comprehension(node, "dict comprehension")

    def visit_GeneratorExp(self, node: ast.GeneratorExp) -> Any:
        return self._comprehension(node, "generator expression")

    def _comprehension(self, node: ast.expr, kind: str) -> ast.expr:
        # Comprehensions have their own scope in Python 3; inserting probes into
        # the element expression changes name resolution.  Declined, not guessed.
        self._skip(node, kind, f"{kind} is traced at statement level only")
        return node


# ----------------------------------------------------------------------
# helpers
# ----------------------------------------------------------------------
def _fill(node: ast.AST, src: ast.AST) -> ast.AST:
    """Give freshly built nodes the location of the statement they came from.

    Keeping original line numbers on inserted probes is what lets the compiled
    code object carry the *user's* line numbers, so tracebacks stay meaningful.
    """
    line = getattr(src, "lineno", 1)
    col = getattr(src, "col_offset", 0)
    for child in ast.walk(node):
        if isinstance(child, (ast.expr, ast.stmt)) and getattr(child, "lineno", None) is None:
            child.lineno = line
            child.col_offset = col
            child.end_lineno = getattr(src, "end_lineno", line)
            child.end_col_offset = getattr(src, "end_col_offset", col)
    return node


def _is_docstring(stmt: ast.stmt) -> bool:
    return (
        isinstance(stmt, ast.Expr)
        and isinstance(stmt.value, ast.Constant)
        and isinstance(stmt.value.value, str)
    )


def _contains_yield(node: ast.AST) -> bool:
    """True if ``node``'s own body yields (nested functions do not count)."""
    for child in ast.iter_child_nodes(node):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(child, (ast.Yield, ast.YieldFrom)):
            return True
        if _contains_yield(child):
            return True
    return False


def _target_names(targets: list[ast.expr]) -> list[str]:
    names: list[str] = []
    for t in targets:
        for node in ast.walk(t):
            if isinstance(node, ast.Name) and node.id not in names:
                names.append(node.id)
    return names


def _src(node: ast.AST) -> str:
    try:
        return ast.unparse(node)[:160]
    except Exception:  # pragma: no cover
        return ""


def _exc_name(node: ast.expr | None) -> str:
    if node is None:
        return "Exception"
    try:
        return ast.unparse(node)
    except Exception:  # pragma: no cover
        return "Exception"


def instrument(source: str, granularity: str = "standard",
               filename: str = "<algostudio>") -> tuple[ast.Module, InstrumentResult]:
    """Parse and instrument ``source``; returns the tree and the report."""
    tree = ast.parse(source, filename=filename)
    result = Instrumenter(granularity).run(tree)
    return result.tree, result
