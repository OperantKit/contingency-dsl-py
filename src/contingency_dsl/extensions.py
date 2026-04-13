"""Extension mechanism for contingency-dsl (§4.7).

Defines the ExtensionModule Protocol and ExtensionRegistry for composing
orthogonal annotation dimensions (stimulus-ext, social-ext, etc.).

Extensions add @-prefixed annotations to schedule expressions without
modifying the base CFG grammar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Protocol, Sequence, runtime_checkable


@runtime_checkable
class ExtensionModule(Protocol):
    """Contract for a DSL grammar extension that adds an annotation dimension.

    Reference: theory.md §4.7.4
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


@dataclass(frozen=True)
class ExtensionRegistry:
    """Collects enabled extensions, validates composition, merges annotation keywords.

    Reference: theory.md §4.7.6
    """

    _extensions: Mapping[str, ExtensionModule] = field(default_factory=dict)
    all_annotation_keywords: frozenset[str] = frozenset()

    @staticmethod
    def build(*extensions: ExtensionModule) -> ExtensionRegistry:
        """Create a registry from one or more extension modules.

        Raises ValueError if:
        - Two extensions claim the same annotation keyword (disjointness violation)
        - An extension's requires set is not satisfied (dependency violation)
        """
        ext_map: dict[str, ExtensionModule] = {}
        all_keywords: set[str] = set()

        for ext in extensions:
            if ext.name in ext_map:
                raise ValueError(f"duplicate extension name: '{ext.name}'")
            ext_map[ext.name] = ext

        # Validate keyword disjointness
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

        # Validate dependency requirements
        available_names = frozenset(ext_map.keys())
        for ext in extensions:
            missing = ext.requires - available_names
            if missing:
                raise ValueError(
                    f"extension '{ext.name}' requires {missing} "
                    f"but only {available_names} are registered"
                )

        return ExtensionRegistry(
            _extensions=ext_map,
            all_annotation_keywords=frozenset(all_keywords),
        )

    def get(self, name: str) -> ExtensionModule:
        """Get an extension by name. Raises KeyError if not found."""
        return self._extensions[name]

    def __contains__(self, name: str) -> bool:
        return name in self._extensions

    def __iter__(self):
        return iter(self._extensions.values())
