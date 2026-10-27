# 被动执行轨迹的因果图、祖先与后继关系。
from __future__ import annotations

from dataclasses import dataclass
from product.backend.domain.verification.trace import ExecutionTrace, TraceEvent
from .models import _Candidate


@dataclass(frozen=True, slots=True)
class _Graph:
    by_id: dict[str, TraceEvent]
    parents: dict[str, frozenset[str]]
    children: dict[str, frozenset[str]]
    ancestors: dict[str, frozenset[str]]
    descendants: dict[str, frozenset[str]]
    depth: dict[str, int]


def _build_graph(trace: ExecutionTrace) -> _Graph:
    by_id = {event.event_id: event for event in trace.events}
    parents = {
        event_id: frozenset(event.parent_event_ids) for event_id, event in by_id.items()
    }
    mutable_children = {event_id: set() for event_id in by_id}
    for event_id, parent_ids in parents.items():
        for parent_id in parent_ids:
            mutable_children[parent_id].add(event_id)
    children = {
        event_id: frozenset(child_ids)
        for event_id, child_ids in mutable_children.items()
    }
    ancestor_cache: dict[str, frozenset[str]] = {}
    descendant_cache: dict[str, frozenset[str]] = {}
    depth_cache: dict[str, int] = {}

    def ancestors(event_id: str) -> frozenset[str]:
        if event_id not in ancestor_cache:
            ancestor_cache[event_id] = frozenset(
                parent_id
                for direct_parent in parents[event_id]
                for parent_id in (direct_parent, *ancestors(direct_parent))
            )
        return ancestor_cache[event_id]

    def descendants(event_id: str) -> frozenset[str]:
        if event_id not in descendant_cache:
            descendant_cache[event_id] = frozenset(
                child_id
                for direct_child in children[event_id]
                for child_id in (direct_child, *descendants(direct_child))
            )
        return descendant_cache[event_id]

    def depth(event_id: str) -> int:
        if event_id not in depth_cache:
            depth_cache[event_id] = (
                0
                if not parents[event_id]
                else 1 + max(depth(parent_id) for parent_id in parents[event_id])
            )
        return depth_cache[event_id]

    for event_id in by_id:
        ancestors(event_id)
        descendants(event_id)
        depth(event_id)
    return _Graph(
        by_id=by_id,
        parents=parents,
        children=children,
        ancestors=ancestor_cache,
        descendants=descendant_cache,
        depth=depth_cache,
    )


def _parent_roles(event: TraceEvent, graph: _Graph) -> tuple[str, ...]:
    return tuple(
        sorted(graph.by_id[parent_id].kind.value for parent_id in event.parent_event_ids)
    )


def _event_business_key(event: TraceEvent, graph: _Graph) -> tuple[object, ...]:
    return (
        graph.depth[event.event_id],
        event.action_id,
        event.resource_ids,
        event.kind.value,
        event.effect_id or "",
        _parent_roles(event, graph),
        event.semantic_key,
        event.event_id,
    )


def _downstream_events(
    primary: _Candidate,
    candidates: list[_Candidate],
    protected: tuple[TraceEvent, ...],
    graph: _Graph,
) -> tuple[str, ...]:
    related = {
        event_id
        for event_id in graph.descendants[primary.event_id]
        if any(
            event_id == event.event_id
            or event_id in graph.ancestors[event.event_id]
            or event_id in graph.descendants[event.event_id]
            for event in protected
        )
    }
    related.update(
        candidate.event_id
        for candidate in candidates
        if candidate.event_id in graph.descendants[primary.event_id]
    )
    return tuple(
        sorted(
            related,
            key=lambda event_id: _event_business_key(graph.by_id[event_id], graph),
        )
    )
