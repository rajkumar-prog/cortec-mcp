"""Tests for cortec.graph — knowledge graph construction and traversal."""

import json
import pytest
from cortec import graph as graph_module


def _mem(id_, type_="general", tags=None, related_to=None, project="default"):
    return {
        "id": id_,
        "type": type_,
        "project": project,
        "summary": f"Summary of {id_}",
        "source": "session",
        "confidence": 0.7,
        "tags": json.dumps(tags or []),
        "related_to": json.dumps(related_to or []),
        "created_at": "2024-01-01T00:00:00",
    }


# ── build ─────────────────────────────────────────────────────────────────────

def test_build_empty():
    G = graph_module.build([])
    assert G.number_of_nodes() == 0
    assert G.number_of_edges() == 0


def test_build_nodes_added():
    mems = [_mem("a1"), _mem("b2"), _mem("c3")]
    G = graph_module.build(mems)
    assert G.number_of_nodes() == 3
    assert "a1" in G


def test_build_explicit_edge():
    mems = [_mem("a1", related_to=["b2"]), _mem("b2")]
    G = graph_module.build(mems)
    assert G.has_edge("a1", "b2")
    assert G["a1"]["b2"]["weight"] == 1.0
    assert G["a1"]["b2"]["reason"] == "explicit"


def test_build_explicit_edge_bidirectional_ignored_for_unknown():
    # only a1 lists b2 in related_to; b2 doesn't list anything not in graph
    mems = [_mem("a1", related_to=["b2"]), _mem("b2")]
    G = graph_module.build(mems)
    assert G.has_edge("a1", "b2")
    assert not G.has_edge("b2", "c9")  # c9 not a node


def test_build_explicit_edge_missing_target_skipped():
    mems = [_mem("a1", related_to=["zzz"])]
    G = graph_module.build(mems)
    assert G.number_of_edges() == 0


def test_build_shared_tag_edge():
    mems = [_mem("a1", tags=["python"]), _mem("b2", tags=["python"])]
    G = graph_module.build(mems)
    assert G.has_edge("a1", "b2")
    assert G["a1"]["b2"]["weight"] == 0.7
    assert "shared_tag" in G["a1"]["b2"]["reason"]


def test_build_same_type_edge():
    mems = [_mem("a1", type_="bug"), _mem("b2", type_="bug")]
    G = graph_module.build(mems)
    assert G.has_edge("a1", "b2")
    assert G["a1"]["b2"]["weight"] == 0.4
    assert G["a1"]["b2"]["reason"] == "same_type"


def test_build_explicit_takes_priority_over_tag():
    mems = [
        _mem("a1", tags=["python"], related_to=["b2"]),
        _mem("b2", tags=["python"]),
    ]
    G = graph_module.build(mems)
    # explicit link was added first; shared_tag should not overwrite it
    assert G.has_edge("a1", "b2")
    assert G["a1"]["b2"]["weight"] == 1.0
    assert G["a1"]["b2"]["reason"] == "explicit"


def test_build_different_projects_no_same_type_edge():
    mems = [
        _mem("a1", type_="bug", project="proj_a"),
        _mem("b2", type_="bug", project="proj_b"),
    ]
    G = graph_module.build(mems)
    # same_type edge only connects memories in the same project
    assert not G.has_edge("a1", "b2")


def test_build_node_attributes():
    mems = [_mem("a1", type_="decision", tags=["infra"])]
    G = graph_module.build(mems)
    node = G.nodes["a1"]
    assert node["type"] == "decision"
    assert node["tags"] == ["infra"]
    assert node["project"] == "default"


# ── neighbors ─────────────────────────────────────────────────────────────────

def test_neighbors_empty_graph():
    G = graph_module.build([])
    result = graph_module.neighbors(G, "nonexistent")
    assert result == []


def test_neighbors_no_edges():
    # different types + different projects → no same_type edge
    mems = [_mem("a1", type_="bug", project="p1"), _mem("b2", type_="fix", project="p2")]
    G = graph_module.build(mems)
    nbs = graph_module.neighbors(G, "a1")
    assert nbs == []


def test_neighbors_direct():
    # give each memory a unique type to suppress same_type edges
    mems = [
        _mem("a1", type_="decision", related_to=["b2"]),
        _mem("b2", type_="fix"),
        _mem("c3", type_="bug"),
    ]
    G = graph_module.build(mems)
    nbs = graph_module.neighbors(G, "a1", depth=1)
    ids = [n["id"] for n in nbs]
    assert "b2" in ids
    assert "a1" not in ids


def test_neighbors_depth_2():
    # chain: a1 →(explicit) b2 →(explicit) c3, all distinct types → depth matters
    mems = [
        _mem("a1", type_="decision", related_to=["b2"]),
        _mem("b2", type_="fix", related_to=["c3"]),
        _mem("c3", type_="bug"),
    ]
    G = graph_module.build(mems)
    nbs_d1 = graph_module.neighbors(G, "a1", depth=1)
    nbs_d2 = graph_module.neighbors(G, "a1", depth=2)
    assert len(nbs_d1) == 1
    assert len(nbs_d2) == 2
    assert any(n["id"] == "c3" for n in nbs_d2)


def test_neighbors_sorted_by_weight_desc():
    mems = [
        _mem("a1", related_to=["b2"], tags=["t"]),
        _mem("b2", tags=["t"]),
        _mem("c3", tags=["t"]),
    ]
    G = graph_module.build(mems)
    nbs = graph_module.neighbors(G, "a1", depth=1)
    weights = [n["weight"] for n in nbs]
    assert weights == sorted(weights, reverse=True)


def test_neighbors_connection_field_indirect():
    # distinct types to ensure c3 is only reachable via b2, not direct same_type edge
    mems = [
        _mem("a1", type_="decision", related_to=["b2"]),
        _mem("b2", type_="fix", related_to=["c3"]),
        _mem("c3", type_="bug"),
    ]
    G = graph_module.build(mems)
    nbs = graph_module.neighbors(G, "a1", depth=2)
    c3_nb = next(n for n in nbs if n["id"] == "c3")
    assert c3_nb["connection"] == "indirect"


# ── summary ───────────────────────────────────────────────────────────────────

def test_summary_empty():
    G = graph_module.build([])
    s = graph_module.summary(G)
    assert s["nodes"] == 0
    assert s["edges"] == 0
    assert s["components"] == 0


def test_summary_nodes_and_edges():
    mems = [_mem("a1", related_to=["b2"]), _mem("b2")]
    G = graph_module.build(mems)
    s = graph_module.summary(G)
    assert s["nodes"] == 2
    assert s["edges"] >= 1


def test_summary_components():
    mems = [
        _mem("a1", related_to=["b2"]),
        _mem("b2"),
        _mem("c3"),  # isolated
    ]
    G = graph_module.build(mems)
    s = graph_module.summary(G)
    # a1-b2 are one component; c3 is isolated (unless same_type links them)
    assert s["components"] >= 1


def test_summary_most_connected():
    mems = [
        _mem("hub", related_to=["a1", "b2", "c3"]),
        _mem("a1"),
        _mem("b2"),
        _mem("c3"),
    ]
    G = graph_module.build(mems)
    s = graph_module.summary(G)
    assert s["most_connected"] is not None
    assert s["most_connected"]["id"] == "hub"
    assert s["most_connected"]["degree"] >= 3


def test_summary_edge_breakdown_explicit():
    mems = [_mem("a1", related_to=["b2"]), _mem("b2")]
    G = graph_module.build(mems)
    s = graph_module.summary(G)
    assert "explicit" in s["edge_breakdown"]
