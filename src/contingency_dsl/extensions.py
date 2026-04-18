"""Extension mechanism for contingency-dsl (§4.7).

Defines the ExtensionModule Protocol and ExtensionRegistry for composing
orthogonal extension dimensions.

Two hook shapes are supported on the same Protocol, and an extension may
implement either or both:

* **Annotation extensions** contribute `@`-prefixed annotation keywords
  (``@reinforcer``, ``@sd``). They add metadata to schedule expressions
  without changing the base CFG.
* **Primitive extensions** contribute identifier-headed primitives
  (``Blocking(...)``, ``Renewal(...)``). They extend the expression head
  at the ``ExtensionRespondentPrimitive`` / ``ExtensionOperantPrimitive``
  boundary described in ``spec/en/respondent/grammar.md``.

Both dimensions are orthogonal and keyword-disjoint: no two extensions may
claim the same annotation keyword, and no two extensions may claim the
same primitive identifier. The two namespaces are separate, so an
extension may legally reuse a name between dimensions (e.g. an annotation
keyword ``foo`` and a primitive identifier ``Foo`` can coexist).
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Protocol, Sequence, runtime_checkable


class CyclicDependencyError(ValueError):
    """Raised when extension dependencies form a cycle."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        path = " → ".join(cycle)
        super().__init__(f"cyclic dependency detected: {path}")


@runtime_checkable
class ExtensionModule(Protocol):
    """Contract for a DSL grammar extension.

    All members are required by Protocol but the primitive-dimension
    members (``primitive_keywords`` and ``parse_primitive``) have
    meaningful defaults: an annotation-only extension returns an empty
    ``primitive_keywords`` set and raises ``UnknownPrimitiveError`` from
    ``parse_primitive``. The default implementations are provided by
    :class:`AnnotationOnlyMixin` for extensions that do not need the
    primitive hook.

    Reference: theory.md §4.7.4 (annotation dimension) and
    ``spec/en/respondent/grammar.md §Respondent Extension Point``
    (primitive dimension).
    """

    name: ClassVar[str]
    version: ClassVar[str]

    @property
    def annotation_keywords(self) -> frozenset[str]:
        """Reserved annotation keywords (e.g. frozenset({"reinforcer", "sd"})).

        Added to the parser's reserved-word set to prevent collisions.
        The '@' prefix is implicit — return bare names.
        """
        ...

    @property
    def annotation_types(self) -> Mapping[str, type]:
        """Map annotation keyword -> frozen dataclass type for static validation."""
        ...

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        """Extension-specific semantic validation.

        Returns a list of diagnostic messages (empty = valid).
        """
        ...

    @property
    def requires(self) -> frozenset[str]:
        """Names of other ExtensionModules this one depends on.

        E.g. social-ext may require stimulus-ext for reinforcer references.
        """
        ...


class UnknownPrimitiveError(KeyError):
    """Raised when an unknown primitive identifier is dispatched."""


def _default_primitive_keywords(ext: Any) -> frozenset[str]:
    """Return the extension's primitive keyword set, or empty if unset."""
    value = getattr(ext, "primitive_keywords", None)
    if value is None:
        return frozenset()
    if isinstance(value, frozenset):
        return value
    return frozenset(value)


def _default_parse_primitive(
    ext: Any,
    name: str,
    positional_args: list[Any] | tuple[Any, ...] | None,
    keyword_args: Mapping[str, Any] | None,
) -> Any:
    """Dispatch to the extension's ``parse_primitive`` if it has one.

    Raises ``UnknownPrimitiveError`` if the extension does not declare
    ``name`` in its ``primitive_keywords`` set. Callers (principally
    :class:`ExtensionRegistry`) are expected to have already routed the
    call to the correct extension, so this function primarily guards
    against misrouted calls.
    """
    hook = getattr(ext, "parse_primitive", None)
    if hook is None or name not in _default_primitive_keywords(ext):
        raise UnknownPrimitiveError(
            f"extension '{getattr(ext, 'name', type(ext).__name__)}' "
            f"does not define primitive '{name}'"
        )
    return hook(name, positional_args, keyword_args)


@dataclass(frozen=True)
class ExtensionRegistry:
    """Collects enabled extensions, validates composition, merges annotation keywords.

    Reference: theory.md §4.7.6
    """

    _extensions: Mapping[str, ExtensionModule] = field(default_factory=dict)
    all_annotation_keywords: frozenset[str] = frozenset()
    all_primitive_keywords: frozenset[str] = frozenset()
    _primitive_owner: Mapping[str, ExtensionModule] = field(default_factory=dict)

    @staticmethod
    def build(*extensions: ExtensionModule) -> ExtensionRegistry:
        """Create a registry from one or more extension modules.

        Raises ValueError if:
        - Two extensions claim the same annotation keyword (disjointness violation)
        - Two extensions claim the same primitive identifier (disjointness violation)
        - An extension's requires set is not satisfied (dependency violation)
        """
        ext_map: dict[str, ExtensionModule] = {}
        all_keywords: set[str] = set()
        all_primitives: set[str] = set()
        primitive_owner: dict[str, ExtensionModule] = {}

        for ext in extensions:
            if ext.name in ext_map:
                raise ValueError(f"duplicate extension name: '{ext.name}'")
            ext_map[ext.name] = ext

        # Validate annotation keyword disjointness
        for ext in extensions:
            for kw in ext.annotation_keywords:
                if kw in all_keywords:
                    # Find the conflicting extension
                    for other in extensions:
                        if other is not ext and kw in other.annotation_keywords:
                            raise ValueError(
                                f"annotation keyword '@{kw}' claimed by both "
                                f"'{ext.name}' and '{other.name}'"
                            )
                all_keywords.add(kw)

        # Validate primitive identifier disjointness
        for ext in extensions:
            for prim in _default_primitive_keywords(ext):
                if prim in all_primitives:
                    for other in extensions:
                        if other is not ext and prim in _default_primitive_keywords(other):
                            raise ValueError(
                                f"primitive identifier '{prim}' claimed by both "
                                f"'{ext.name}' and '{other.name}'"
                            )
                all_primitives.add(prim)
                primitive_owner[prim] = ext

        # Validate dependency requirements
        available_names = frozenset(ext_map.keys())
        for ext in extensions:
            missing = ext.requires - available_names
            if missing:
                raise ValueError(
                    f"extension '{ext.name}' requires {missing} "
                    f"but only {available_names} are registered"
                )

        # Validate acyclicity via topological sort (Kahn's algorithm)
        graph: dict[str, set[str]] = {
            ext.name: set(ext.requires) for ext in extensions
        }
        in_degree: dict[str, int] = {name: 0 for name in graph}
        for deps in graph.values():
            for dep in deps:
                in_degree[dep] = in_degree.get(dep, 0) + 1

        queue: deque[str] = deque(
            name for name, deg in in_degree.items() if deg == 0
        )
        visited = 0
        while queue:
            node = queue.popleft()
            visited += 1
            for dep in graph.get(node, set()):
                in_degree[dep] -= 1
                if in_degree[dep] == 0:
                    queue.append(dep)

        if visited != len(graph):
            # Find one cycle for the error message via DFS
            cycle = _find_cycle(graph)
            raise CyclicDependencyError(cycle)

        return ExtensionRegistry(
            _extensions=ext_map,
            all_annotation_keywords=frozenset(all_keywords),
            all_primitive_keywords=frozenset(all_primitives),
            _primitive_owner=primitive_owner,
        )

    def get(self, name: str) -> ExtensionModule:
        """Get an extension by name. Raises KeyError if not found."""
        return self._extensions[name]

    def parse_primitive(
        self,
        name: str,
        positional_args: list[Any] | tuple[Any, ...] | None = None,
        keyword_args: Mapping[str, Any] | None = None,
    ) -> Any:
        """Dispatch a primitive call to the registered extension that owns ``name``.

        Raises :class:`UnknownPrimitiveError` if no registered extension
        claims ``name`` as a primitive identifier.
        """
        owner = self._primitive_owner.get(name)
        if owner is None:
            raise UnknownPrimitiveError(
                f"no registered extension defines primitive '{name}'. "
                f"Known: {sorted(self.all_primitive_keywords)}"
            )
        return _default_parse_primitive(owner, name, positional_args, keyword_args)

    def __contains__(self, name: str) -> bool:
        return name in self._extensions

    def __iter__(self):
        return iter(self._extensions.values())


def _find_cycle(graph: dict[str, set[str]]) -> list[str]:
    """Find one cycle in *graph* via DFS. Returns the cycle as a list of names."""
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {n: WHITE for n in graph}
    parent: dict[str, str | None] = {n: None for n in graph}

    for start in graph:
        if color[start] != WHITE:
            continue
        stack = [start]
        while stack:
            node = stack[-1]
            if color[node] == WHITE:
                color[node] = GRAY
                for neighbour in graph.get(node, set()):
                    if color[neighbour] == GRAY:
                        # Reconstruct cycle
                        cycle = [neighbour, node]
                        cur = node
                        while cur != neighbour:
                            cur = parent[cur]  # type: ignore[assignment]
                            if cur is None:
                                break
                            cycle.append(cur)
                        cycle.reverse()
                        cycle.append(cycle[0])  # close the loop
                        return cycle
                    if color[neighbour] == WHITE:
                        parent[neighbour] = node
                        stack.append(neighbour)
            else:
                color[node] = BLACK
                stack.pop()
    return []  # unreachable when called after Kahn's detects a cycle
