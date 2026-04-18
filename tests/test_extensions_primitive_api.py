"""Tests for the primitive-extension API on `ExtensionModule` / `ExtensionRegistry`.

These cover the extension-point hook that lets third-party packages register
full identifier-headed primitives (e.g. `Blocking(...)`, `Renewal(...)`),
distinct from the earlier annotation-extension hook (`@reinforcer(...)`).

Both hooks are optional; an extension may implement one, the other, or
both. Backward compatibility requires that an annotation-only extension
continues to register and dispatch without surfacing any primitive-API
attributes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, ClassVar, Mapping, Sequence

import pytest

from contingency_dsl.extensions import ExtensionModule, ExtensionRegistry


# ---------------------------------------------------------------------------
# Fixtures — test doubles that implement the Protocol in different ways
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _AnnotationOnlyExtension:
    """An extension that exposes only the annotation hook (no primitives)."""

    name: ClassVar[str] = "annotation-only"
    version: ClassVar[str] = "test"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset({"foo"})

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {"foo": str}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()


@dataclass(frozen=True)
class _PrimitiveOnlyExtension:
    """An extension with only the primitive hook — a Tier B-shaped extension."""

    name: ClassVar[str] = "primitive-only"
    version: ClassVar[str] = "test"

    _calls: list = field(default_factory=list)

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset()

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @property
    def primitive_keywords(self) -> frozenset[str]:
        return frozenset({"MyProc", "OtherProc"})

    def parse_primitive(
        self,
        name: str,
        positional_args: list[Any] | tuple[Any, ...] | None = None,
        keyword_args: Mapping[str, Any] | None = None,
    ) -> dict:
        self._calls.append((name, tuple(positional_args or ()), dict(keyword_args or {})))
        return {"type": name, "kwargs": dict(keyword_args or {})}


@dataclass(frozen=True)
class _SecondPrimitiveExtension:
    """Second primitive-only extension for collision and ordering tests."""

    name: ClassVar[str] = "second-primitive"
    version: ClassVar[str] = "test"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset()

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @property
    def primitive_keywords(self) -> frozenset[str]:
        return frozenset({"ThirdProc"})

    def parse_primitive(
        self,
        name: str,
        positional_args: list[Any] | tuple[Any, ...] | None = None,
        keyword_args: Mapping[str, Any] | None = None,
    ) -> dict:
        return {"type": name, "source": "second"}


@dataclass(frozen=True)
class _CollidingPrimitiveExtension:
    """Second extension that claims the same identifier as `_PrimitiveOnlyExtension`."""

    name: ClassVar[str] = "colliding-primitive"
    version: ClassVar[str] = "test"

    @property
    def annotation_keywords(self) -> frozenset[str]:
        return frozenset()

    @property
    def annotation_types(self) -> Mapping[str, type]:
        return {}

    def validate(self, annotations: Sequence[Any]) -> list[str]:
        return []

    @property
    def requires(self) -> frozenset[str]:
        return frozenset()

    @property
    def primitive_keywords(self) -> frozenset[str]:
        return frozenset({"MyProc"})  # collides with _PrimitiveOnlyExtension

    def parse_primitive(
        self,
        name: str,
        positional_args: list[Any] | tuple[Any, ...] | None = None,
        keyword_args: Mapping[str, Any] | None = None,
    ) -> dict:
        return {"type": name, "source": "colliding"}


# ---------------------------------------------------------------------------
# Backward compatibility: annotation-only extension still works
# ---------------------------------------------------------------------------


def test_annotation_only_extension_registers_without_primitive_api():
    registry = ExtensionRegistry.build(_AnnotationOnlyExtension())
    assert "foo" in registry.all_annotation_keywords
    assert registry.all_primitive_keywords == frozenset()


def test_annotation_only_extension_has_empty_primitive_dispatch_table():
    registry = ExtensionRegistry.build(_AnnotationOnlyExtension())
    with pytest.raises((KeyError, ValueError)):
        registry.parse_primitive("NotExisting", [], {})


# ---------------------------------------------------------------------------
# Primitive API surface
# ---------------------------------------------------------------------------


def test_primitive_only_extension_exposes_primitive_keywords():
    ext = _PrimitiveOnlyExtension()
    registry = ExtensionRegistry.build(ext)
    assert registry.all_primitive_keywords == frozenset({"MyProc", "OtherProc"})


def test_primitive_dispatch_reaches_extension():
    ext = _PrimitiveOnlyExtension()
    registry = ExtensionRegistry.build(ext)
    result = registry.parse_primitive(
        "MyProc",
        positional_args=[],
        keyword_args={"phase1": "a", "phase2": "b"},
    )
    assert result == {"type": "MyProc", "kwargs": {"phase1": "a", "phase2": "b"}}
    assert ext._calls == [("MyProc", (), {"phase1": "a", "phase2": "b"})]


def test_primitive_dispatch_unknown_name_raises():
    registry = ExtensionRegistry.build(_PrimitiveOnlyExtension())
    with pytest.raises((KeyError, ValueError)):
        registry.parse_primitive("Unknown", [], {})


# ---------------------------------------------------------------------------
# Registry composition — primitive keyword disjointness
# ---------------------------------------------------------------------------


def test_disjoint_primitive_extensions_compose():
    registry = ExtensionRegistry.build(
        _PrimitiveOnlyExtension(), _SecondPrimitiveExtension()
    )
    assert registry.all_primitive_keywords == frozenset(
        {"MyProc", "OtherProc", "ThirdProc"}
    )
    second = registry.parse_primitive("ThirdProc", [], {})
    assert second == {"type": "ThirdProc", "source": "second"}


def test_colliding_primitive_keyword_raises_on_build():
    with pytest.raises(ValueError, match="MyProc"):
        ExtensionRegistry.build(
            _PrimitiveOnlyExtension(), _CollidingPrimitiveExtension()
        )


# ---------------------------------------------------------------------------
# Annotation + primitive can coexist in one registry
# ---------------------------------------------------------------------------


def test_annotation_and_primitive_extensions_coexist():
    ann = _AnnotationOnlyExtension()
    prim = _PrimitiveOnlyExtension()
    registry = ExtensionRegistry.build(ann, prim)
    assert registry.all_annotation_keywords == frozenset({"foo"})
    assert registry.all_primitive_keywords == frozenset({"MyProc", "OtherProc"})

    # Annotation and primitive namespaces are separate — an extension may
    # reuse a name from the other dimension without collision.
    result = registry.parse_primitive("MyProc", [], {})
    assert result["type"] == "MyProc"


# ---------------------------------------------------------------------------
# Protocol conformance — the test doubles must satisfy the Protocol
# ---------------------------------------------------------------------------


def test_annotation_only_extension_satisfies_protocol():
    ext = _AnnotationOnlyExtension()
    assert isinstance(ext, ExtensionModule)


def test_primitive_only_extension_satisfies_protocol():
    ext = _PrimitiveOnlyExtension()
    assert isinstance(ext, ExtensionModule)
