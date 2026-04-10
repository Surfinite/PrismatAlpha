"""Tests for ob_explorer_data — tree construction, pruning, Wilson CI."""
import sys
sys.path.insert(0, ".")

from tools.ob_explorer_data import (
    build_tree,
    count_nodes,
    prune_tree,
    wilson_ci,
)


def test_wilson_ci_zero():
    assert wilson_ci(0, 0) == (0.0, 0.0)


def test_wilson_ci_perfect():
    lo, hi = wilson_ci(100, 100)
    assert lo > 0.95
    assert hi >= 1.0 - 1e-9


def test_wilson_ci_half():
    lo, hi = wilson_ci(50, 100)
    assert 0.39 < lo < 0.41
    assert 0.59 < hi < 0.61


def test_build_tree_empty():
    tree = build_tree([], 0, 3)
    assert tree["count"] == 0
    assert tree["buy_abbrev"] == "6D+2E"
    assert tree["children"] == []


def test_build_tree_single_game():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("game1", 2, "Drone,Drone,Engineer", '["Drone","Drone","Engineer"]', 0),
    ]
    tree = build_tree(rows, 0, 3)
    assert tree["count"] == 1
    assert tree["win_rate"] == 1.0  # player 0 won (result=0)
    assert len(tree["children"]) == 1
    assert tree["children"][0]["buy_abbrev"] == "D+D"
    assert tree["children"][0]["count"] == 1
    assert len(tree["children"][0]["children"]) == 1
    assert tree["children"][0]["children"][0]["buy_abbrev"] == "D+D+E"


def test_build_tree_p2_win_rate():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 1),  # P2 wins
        ("game2", 1, "Drone,Drone", '["Drone","Drone"]', 0),  # P1 wins
    ]
    tree = build_tree(rows, 1, 1)  # analyzing as P2
    assert tree["count"] == 2
    assert tree["win_rate"] == 0.5
    assert tree["children"][0]["win_rate"] == 0.5


def test_build_tree_draws_excluded_from_wr():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),  # P1 wins
        ("game2", 1, "Drone,Drone", '["Drone","Drone"]', 2),  # draw
    ]
    tree = build_tree(rows, 0, 1)
    assert tree["count"] == 2
    assert tree["count_decisive"] == 1
    assert tree["count_draws"] == 1
    assert tree["win_rate"] == 1.0  # 1 win / 1 decisive


def test_build_tree_multiset_buys_preserved():
    rows = [
        ("game1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
    ]
    tree = build_tree(rows, 0, 1)
    child = tree["children"][0]
    assert child["buy"] == ["Drone", "Drone"]
    assert "D+D" in child["buy_abbrev"]


def test_prune_frequency():
    rows = [
        ("g1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g2", 1, "Drone,Drone", '["Drone","Drone"]', 1),
        ("g3", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g4", 1, "Drone,Drone", '["Drone","Drone"]', 1),
        ("g5", 1, "Drone,Engineer", '["Drone","Engineer"]', 0),
    ]
    tree = build_tree(rows, 0, 1)
    pruned = prune_tree(tree, [0.25])
    assert len(pruned["children"]) == 1
    assert pruned["other_count"] == 1
    total = sum(c["count"] for c in pruned["children"]) + pruned["other_count"]
    assert total == 5


def test_prune_max_branches():
    rows = []
    buys = ["Drone,Drone", "Drone,Engineer", "Conduit,Drone",
            "Blastforge,Drone", "Animus"]
    seqs = ['["Drone","Drone"]', '["Drone","Engineer"]', '["Conduit","Drone"]',
            '["Blastforge","Drone"]', '["Animus"]']
    for i, (bh, bs) in enumerate(zip(buys, seqs)):
        for j in range(5 - i):
            rows.append((f"g{i}_{j}", 1, bh, bs, 0))

    tree = build_tree(rows, 0, 1)
    pruned = prune_tree(tree, [0.01], max_branches=3)
    assert len(pruned["children"]) == 3
    assert pruned["other_count"] == 3


def test_count_nodes():
    tree = build_tree([], 0, 1)
    assert count_nodes(tree) == 1

    rows = [
        ("g1", 1, "Drone,Drone", '["Drone","Drone"]', 0),
        ("g1", 2, "Drone,Drone,Engineer", '["Drone","Drone","Engineer"]', 0),
    ]
    tree = build_tree(rows, 0, 2)
    assert count_nodes(tree) == 3


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
