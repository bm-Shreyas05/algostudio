"""Python AST -> AlgoStudio IR.

The IR is a *description* of the program, not something we execute (see
docs/04-ir.md).  It exists so that static structure -- functions, loops,
recursion, data structures, unsupported constructs -- is available to the
capability report, the analysis panel and the AI context in a form that is not
Python-specific.

Critically, ``loop_id``/``func_id`` are computed by the same rules the
transformer uses, so static structure and runtime events join on those keys.
"""

from __future__ import annotations

import ast

from ...core import ir
from ...core.events import Loc
from .transformer import func_id_for, loop_id_for

_COLLECTION_KINDS = {
    ast.List: "list",
    ast.Dict: "dict",
    ast.Set: "set",
    ast.Tuple: "tuple",
}
_CONSTRUCTORS = {
    "list": "list", "dict": "dict", "set": "set", "tuple": "tuple",
    "deque": "deque", "defaultdict": "dict", "Counter": "dict",
    "OrderedDict": "dict", "frozenset": "set", "array": "array",
}


class Lowerer(ast.NodeVisitor):
    def __init__(self) -> None:
        self.program = ir.Program(root=ir.Node(ir.MODULE))
        self._func_stack: list[str] = []
        self._loop_depth = 0
        self._node_stack: list[ir.Node] = [self.program.root]

    # ------------------------------------------------------------------
    def lower(self, tree: ast.Module) -> ir.Program:
        for stmt in tree.body:
            self.visit(stmt)
        ir.compute_recursion(self.program.functions)
        return self.program

    def _emit(self, node_kind: str, node: ast.AST, /, **attrs: object) -> ir.Node:
        # positional-only: attrs may legitimately contain a "kind" key
        n = ir.Node(node_kind, _loc(node), dict(attrs))
        self._node_stack[-1].children.append(n)
        return n

    def _descend(self, parent: ir.Node, body: list[ast.stmt]) -> None:
        self._node_stack.append(parent)
        for stmt in body:
            self.visit(stmt)
        self._node_stack.pop()

    # ------------------------------------------------------------------
    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        fid = func_id_for(node, node.name)
        params = (
            [a.arg for a in getattr(node.args, "posonlyargs", [])]
            + [a.arg for a in node.args.args]
            + ([node.args.vararg.arg] if node.args.vararg else [])
            + [a.arg for a in node.args.kwonlyargs]
            + ([node.args.kwarg.arg] if node.args.kwarg else [])
        )
        self.program.functions[fid] = ir.FunctionInfo(
            func_id=fid,
            name=node.name,
            qualname=".".join([*self._func_stack_names(), node.name]),
            params=params,
            line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
        )
        n = self._emit(ir.FUNC_DEF, node, name=node.name, func_id=fid, params=params)
        self._func_stack.append(fid)
        self._descend(n, node.body)
        self._func_stack.pop()

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        n = self._emit(
            ir.UNSUPPORTED, node,
            original_kind="AsyncFunctionDef",
            reason="async functions are not modelled by the event engine",
        )
        self.program.unsupported.append(n)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        n = self._emit(ir.CLASS_DEF, node, name=node.name,
                       bases=[_name_of(b) for b in node.bases])
        self._descend(n, node.body)

    def visit_For(self, node: ast.For) -> None:
        lid = loop_id_for(node)
        var = node.target.id if isinstance(node.target, ast.Name) else None
        self.program.loops[lid] = ir.LoopInfo(
            loop_id=lid, kind="for", line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            depth=self._loop_depth + 1,
            func_id=self._func_stack[-1] if self._func_stack else None,
            var=var,
        )
        n = self._emit(ir.LOOP, node, kind="for", loop_id=lid, var=var,
                       iter=_describe(node.iter))
        self._loop_depth += 1
        self._descend(n, node.body)
        if node.orelse:
            self._descend(n, node.orelse)
        self._loop_depth -= 1
        self._scan_expr(node.iter)

    def visit_While(self, node: ast.While) -> None:
        lid = loop_id_for(node)
        self.program.loops[lid] = ir.LoopInfo(
            loop_id=lid, kind="while", line=node.lineno,
            end_line=getattr(node, "end_lineno", node.lineno) or node.lineno,
            depth=self._loop_depth + 1,
            func_id=self._func_stack[-1] if self._func_stack else None,
        )
        n = self._emit(ir.LOOP, node, kind="while", loop_id=lid,
                       test=_describe(node.test))
        self._loop_depth += 1
        self._descend(n, node.body)
        if node.orelse:
            self._descend(n, node.orelse)
        self._loop_depth -= 1
        self._scan_expr(node.test)

    def visit_If(self, node: ast.If) -> None:
        n = self._emit(ir.IF, node, test=_describe(node.test))
        self._descend(n, node.body)
        if node.orelse:
            self._descend(n, node.orelse)
        self._scan_expr(node.test)

    def visit_Try(self, node: ast.Try) -> None:
        n = self._emit(ir.TRY, node,
                       handlers=[_name_of(h.type) for h in node.handlers])
        self._descend(n, node.body)
        for handler in node.handlers:
            self._descend(n, handler.body)
        self._descend(n, node.orelse)
        self._descend(n, node.finalbody)

    visit_TryStar = visit_Try  # type: ignore[assignment]

    def visit_With(self, node: ast.With) -> None:
        n = self._emit(ir.EXPR_STMT, node, kind="with")
        self._descend(n, node.body)

    def visit_Assign(self, node: ast.Assign) -> None:
        self._emit(
            ir.ASSIGN, node,
            targets=[_describe(t) for t in node.targets],
            value=_describe(node.value),
        )
        self._scan_expr(node.value)

    def visit_AugAssign(self, node: ast.AugAssign) -> None:
        self._emit(ir.AUG_ASSIGN, node, target=_describe(node.target),
                   value=_describe(node.value))
        self._scan_expr(node.value)

    def visit_AnnAssign(self, node: ast.AnnAssign) -> None:
        if node.value is not None:
            self._emit(ir.ASSIGN, node, targets=[_describe(node.target)],
                       value=_describe(node.value))
            self._scan_expr(node.value)

    def visit_Return(self, node: ast.Return) -> None:
        self._emit(ir.RETURN, node,
                   value=_describe(node.value) if node.value else None)
        if node.value is not None:
            self._scan_expr(node.value)

    def visit_Delete(self, node: ast.Delete) -> None:
        self._emit(ir.DELETE, node, targets=[_describe(t) for t in node.targets])

    def visit_Break(self, node: ast.Break) -> None:
        self._emit(ir.BREAK, node)

    def visit_Continue(self, node: ast.Continue) -> None:
        self._emit(ir.CONTINUE, node)

    def visit_Raise(self, node: ast.Raise) -> None:
        self._emit(ir.RAISE, node, exc=_name_of(node.exc))

    def visit_Expr(self, node: ast.Expr) -> None:
        self._emit(ir.EXPR_STMT, node, value=_describe(node.value))
        self._scan_expr(node.value)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            self.program.imports.append(alias.name)
        self._emit(ir.IMPORT, node, names=[a.name for a in node.names])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if node.module:
            self.program.imports.append(node.module)
        self._emit(ir.IMPORT, node, module=node.module,
                   names=[a.name for a in node.names])

    # ------------------------------------------------------------------
    def _scan_expr(self, node: ast.expr | None) -> None:
        """Record data structures constructed and call-graph edges."""
        if node is None:
            return
        for child in ast.walk(node):
            kind = _COLLECTION_KINDS.get(type(child))
            if kind and not isinstance(getattr(child, "ctx", None), ast.Store):
                self.program.collections_created.append(kind)
            elif isinstance(child, ast.Call):
                name = _name_of(child.func)
                if name in _CONSTRUCTORS:
                    self.program.collections_created.append(_CONSTRUCTORS[name])
                if self._func_stack and name:
                    self.program.functions[self._func_stack[-1]].calls.add(name)
                elif name:
                    pass  # module-level calls are not part of the call graph
            elif isinstance(
                child, (ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp)
            ):
                node_ = ir.Node(
                    ir.COMPREHENSION, _loc(child),
                    {"kind": type(child).__name__},
                )
                self._node_stack[-1].children.append(node_)

    def _func_stack_names(self) -> list[str]:
        return [self.program.functions[f].name for f in self._func_stack]


# ----------------------------------------------------------------------
def _loc(node: ast.AST) -> Loc:
    return Loc(
        getattr(node, "lineno", 0),
        getattr(node, "col_offset", 0),
        getattr(node, "end_lineno", 0) or getattr(node, "lineno", 0),
        getattr(node, "end_col_offset", 0) or 0,
    )


def _name_of(node: ast.AST | None) -> str:
    if node is None:
        return ""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Call):
        return _name_of(node.func)
    return ""


def _describe(node: ast.AST | None) -> str:
    if node is None:
        return ""
    try:
        return ast.unparse(node)[:120]
    except Exception:  # pragma: no cover
        return type(node).__name__


def lower(tree: ast.Module) -> ir.Program:
    return Lowerer().lower(tree)
