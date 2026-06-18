"""
Knowledge graph — connects memories by project, type, tags, and explicit links.
Uses NetworkX for graph construction and traversal.
"""

import json
from typing import Any

import networkx as nx


def build(memories: list[dict]) -> nx.Graph:
    """
    Build an undirected graph from a list of memory dicts.

    Nodes are memory IDs with memory metadata as attributes.
    Edges are added for:
      - Explicit related_to links (weight=1.0, reason='explicit')
      - Shared tags between memories (weight=0.7, reason='shared_tag:<tag>')
      - Same type within the same project (weight=0.4, reason='same_type')
    """
    G = nx.Graph()

    for m in memories:
        G.add_node(
            m["id"],
            summary=m.get("summary", "")[:120],
            type=m.get("type", "general"),
            project=m.get("project", "default"),
            source=m.get("source", ""),
            confidence=m.get("confidence", 0.5),
            tags=json.loads(m.get("tags") or "[]"),
            created_at=m.get("created_at", "")[:10],
        )

    # Explicit links
    for m in memories:
        for related_id in json.loads(m.get("related_to") or "[]"):
            if G.has_node(related_id):
                G.add_edge(m["id"], related_id, weight=1.0, reason="explicit")

    # Shared tags
    tag_index: dict[str, list[str]] = {}
    for m in memories:
        for tag in json.loads(m.get("tags") or "[]"):
            tag_index.setdefault(tag, []).append(m["id"])

    for tag, ids in tag_index.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if not G.has_edge(ids[i], ids[j]):
                    G.add_edge(ids[i], ids[j], weight=0.7, reason=f"shared_tag:{tag}")

    # Same type within same project
    type_index: dict[tuple[str, str], list[str]] = {}
    for m in memories:
        key = (m.get("project", "default"), m.get("type", "general"))
        type_index.setdefault(key, []).append(m["id"])

    for (project, type_), ids in type_index.items():
        for i in range(len(ids)):
            for j in range(i + 1, len(ids)):
                if not G.has_edge(ids[i], ids[j]):
                    G.add_edge(ids[i], ids[j], weight=0.4, reason="same_type")

    return G


def neighbors(G: nx.Graph, memory_id: str, depth: int = 1) -> list[dict[str, Any]]:
    """
    Return all nodes reachable within `depth` hops from memory_id.

    Each result includes the neighbor's attributes and the edge reason connecting
    it to the starting node (direct neighbors only for reason field).
    """
    if memory_id not in G:
        return []

    visited = set()
    current_level = {memory_id}

    for _ in range(depth):
        next_level: set[str] = set()
        for node in current_level:
            for nb in G.neighbors(node):
                if nb != memory_id and nb not in visited:
                    next_level.add(nb)
        visited.update(next_level)
        current_level = next_level

    results = []
    for nb_id in visited:
        attrs = dict(G.nodes[nb_id])
        edge_data = G.get_edge_data(memory_id, nb_id)
        attrs["id"] = nb_id
        attrs["connection"] = edge_data.get("reason", "indirect") if edge_data else "indirect"
        attrs["weight"] = edge_data.get("weight", 0.0) if edge_data else 0.0
        results.append(attrs)

    return sorted(results, key=lambda x: -x["weight"])


def summary(G: nx.Graph) -> dict[str, Any]:
    """Return a high-level summary of the graph's structure."""
    if G.number_of_nodes() == 0:
        return {"nodes": 0, "edges": 0, "components": 0, "most_connected": None}

    components = list(nx.connected_components(G))
    degrees = sorted(G.degree(), key=lambda x: -x[1])
    most_connected_id = degrees[0][0] if degrees else None
    most_connected = None
    if most_connected_id:
        most_connected = {
            "id": most_connected_id,
            "degree": degrees[0][1],
            "summary": G.nodes[most_connected_id].get("summary", ""),
        }

    edge_reasons: dict[str, int] = {}
    for _, _, data in G.edges(data=True):
        reason = data.get("reason", "unknown").split(":")[0]
        edge_reasons[reason] = edge_reasons.get(reason, 0) + 1

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "components": len(components),
        "largest_component": max(len(c) for c in components),
        "most_connected": most_connected,
        "edge_breakdown": edge_reasons,
    }
