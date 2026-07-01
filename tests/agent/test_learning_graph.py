"""Behavior contracts for the learning-graph assembler.

Asserts invariants (edges resolve to real nodes, clusters cover every node,
memory cards are represented consistently), never a snapshot of the live skill
catalog — that catalog grows every release and a count assertion would be a
change-detector.
"""

from __future__ import annotations

from agent import learning_graph
from hermes_constants import reset_hermes_home_override, set_hermes_home_override


def _node(name: str, category: str, related=None):
    n = learning_graph.SkillNode(name=name, category=category)
    n.related = list(related or [])
    return n


def test_edges_only_connect_existing_nodes():
    nodes = {
        "a": _node("a", "x", related=["b", "ghost"]),
        "b": _node("b", "x", related=["a"]),
        "c": _node("c", "y"),
    }
    edges = learning_graph.build_edges(nodes)

    # The a→b link is kept once (deduped, undirected); a→ghost is dropped.
    assert edges == [("a", "b")]


def test_density_stats_count_isolated_nodes():
    nodes = {
        "a": _node("a", "x", related=["b"]),
        "b": _node("b", "x", related=["a"]),
        "c": _node("c", "y"),
    }
    stats = learning_graph.density_stats(nodes, learning_graph.build_edges(nodes))

    assert stats["nodes"] == 3
    assert stats["linked_nodes"] == 2
    assert stats["isolated_pct"] == round(100 / 3, 1)


def test_skill_node_timestamp_uses_iso_usage_activity(tmp_path, monkeypatch):
    skill_dir = tmp_path / "skills" / "dev" / "iso-skill"
    skill_dir.mkdir(parents=True)
    skill_md = skill_dir / "SKILL.md"
    skill_md.write_text("---\nname: iso-skill\ncategory: dev\n---\n# ISO\n", encoding="utf-8")

    monkeypatch.setattr(
        learning_graph,
        "_load_usage",
        lambda: {
            "iso-skill": {
                "created_by": "agent",
                "last_used_at": "2026-04-30T12:00:00+00:00",
                "use_count": 1,
            }
        },
    )

    nodes = learning_graph.build_skill_nodes([("profile", tmp_path / "skills")])

    assert nodes["iso-skill"].timestamp == 1_777_550_400


def test_skill_node_tolerates_non_mapping_metadata_from_fallback_parser(tmp_path, monkeypatch):
    """Malformed-but-installed skills must not crash the journey graph.

    Some imported skills have unquoted colons in YAML frontmatter. The shared
    frontmatter parser then falls back to simple key:value parsing, which turns
    nested ``metadata:`` into the string ``""``. The learning graph should still
    render the rest of the skill catalog instead of assuming metadata is a dict.
    """
    skill_dir = tmp_path / "skills" / "openclaw-imports" / "homebrew"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text(
        "---\n"
        "name: homebrew\n"
        "description: Manage packages safely: install/upgrade/list/search/info\n"
        "metadata:\n"
        "  openclaw:\n"
        "    emoji: \"🍺\"\n"
        "---\n"
        "# Homebrew\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        learning_graph,
        "_load_usage",
        lambda: {"homebrew": {"created_by": "agent", "use_count": 1}},
    )

    nodes = learning_graph.build_skill_nodes([("profile", tmp_path / "skills")])

    assert nodes["homebrew"].category == "openclaw-imports"
    assert nodes["homebrew"].related == []


def test_memory_is_cards_split_on_separator(tmp_path):
    home = tmp_path / ".hermes"
    (home / "memories").mkdir(parents=True)
    (home / "memories" / "MEMORY.md").write_text(
        "Project uses pytest with xdist\n§\nUser prefers concise responses",
        encoding="utf-8",
    )
    token = set_hermes_home_override(home)
    try:
        graph = learning_graph.build_learning_graph()
    finally:
        reset_hermes_home_override(token)

    titles = [c["title"] for c in graph["memory"]]
    assert "Project uses pytest with xdist" in titles
    assert "User prefers concise responses" in titles
    # Memory cards remain typed cards and also appear as memory-kind nodes.
    assert all(c["source"] in {"memory", "profile"} for c in graph["memory"])
    assert all("timestamp" in c for c in graph["memory"])
    assert any(n["kind"] == "memory" for n in graph["nodes"])


def test_full_payload_shape_and_edge_integrity(tmp_path):
    home = tmp_path / ".hermes"
    home.mkdir()
    token = set_hermes_home_override(home)
    try:
        graph = learning_graph.build_learning_graph()
    finally:
        reset_hermes_home_override(token)

    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
    # Every node's category appears in the cluster list.
    cluster_cats = {c["category"] for c in graph["clusters"]}
    assert all(n["category"] in cluster_cats for n in graph["nodes"])
    skill_nodes = [n for n in graph["nodes"] if n["kind"] == "skill"]
    assert graph["stats"]["nodes"] == len(skill_nodes)
    assert graph["stats"]["memory_nodes"] == len(graph["memory"])
    assert all("timestamp" in n for n in graph["nodes"])
