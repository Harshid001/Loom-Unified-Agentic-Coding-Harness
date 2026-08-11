

from loom.context.budget import (
    RELEVANCE_WEIGHTS,
    BudgetAssembly,
    ContextBudgetManager,
)
from loom.repo_intel.call_graph import CallGraph, GraphEdge
from loom.repo_intel.parser import Symbol


class TestTokenEstimation:
    def test_empty_string(self):
        b = ContextBudgetManager()
        assert b.estimate_tokens("") == 1

    def test_english_text(self):
        b = ContextBudgetManager()
        assert b.estimate_tokens("hello world") == 2

    def test_long_code(self):
        b = ContextBudgetManager()
        code = "def foo():\n    return 42\n" * 100
        assert b.estimate_tokens(code) > 0


class TestBudgetLimits:
    def test_mock_model_budget(self):
        b = ContextBudgetManager(model_name="mock")
        limits = b.budget_limits
        assert limits["system"] == int(4096 * 0.15)
        assert limits["symbols"] == int(4096 * 0.55)
        assert limits["memory"] == int(4096 * 0.20)
        assert limits["headroom"] == int(4096 * 0.10)
        assert limits["total"] == 4096

    def test_claude_model_budget(self):
        b = ContextBudgetManager(model_name="claude-3-5-sonnet-20241022")
        limits = b.budget_limits
        assert limits["total"] == 200000

    def test_unknown_model_defaults(self):
        b = ContextBudgetManager(model_name="nonexistent-model")
        assert b.budget_limits["total"] == 128000


class TestTFIDFScoring:
    def test_exact_match_scores_higher(self):
        b = ContextBudgetManager()
        score = b._compute_tfidf("calculate total price", "fix calculate total price bug", ["calculate total price"])
        assert score > 0

    def test_no_match_scores_zero(self):
        b = ContextBudgetManager()
        score = b._compute_tfidf("unrelated text", "fix calculate bug", ["unrelated text"])
        assert score == 0.0

    def test_empty_issue_scores_zero(self):
        b = ContextBudgetManager()
        score = b._compute_tfidf("some symbol text", "", ["some symbol text"])
        assert score == 0.0

    def test_multiple_corpus_docs(self):
        b = ContextBudgetManager()
        score = b._compute_tfidf(
            "calculate total price with tax",
            "fix the price calculation bug in billing",
            [
                "calculate total price with tax",
                "unrelated auth module",
                "database migration helper",
            ],
        )
        assert score > 0


class TestGraphProximity:
    def test_touched_file_is_max_proximity(self):
        b = ContextBudgetManager()
        sym = Symbol(name="foo", kind="function", file_path="src/auth/login.py", line_number=10)
        score = b._graph_proximity(sym, ["src/auth/login.py"], None)
        assert score == 1.0

    def test_touched_file_always_max_regardless_of_graph(self):
        b = ContextBudgetManager()
        graph = CallGraph(
            nodes={"a.py", "b.py"},
            edges=[GraphEdge(source_file="a.py", target_file="b.py", symbol_name="x")],
        )
        sym = Symbol(name="foo", kind="function", file_path="a.py", line_number=1)
        score = b._graph_proximity(sym, ["a.py"], graph)
        assert score == 1.0

    def test_no_callgraph_no_touched_is_default(self):
        b = ContextBudgetManager()
        sym = Symbol(name="bar", kind="function", file_path="src/other.py", line_number=5)
        score = b._graph_proximity(sym, ["src/main.py"], None)
        assert score == 0.5

    def test_connected_file_via_edge(self):
        b = ContextBudgetManager()
        edge = GraphEdge(source_file="src/auth/login.py", target_file="src/utils/helpers.py", symbol_name="hash_password")
        graph = CallGraph(
            nodes={"src/auth/login.py", "src/utils/helpers.py"},
            edges=[edge],
        )
        sym = Symbol(name="hash_password", kind="function", file_path="src/utils/helpers.py", line_number=10)
        score = b._graph_proximity(sym, ["src/auth/login.py"], graph)
        assert score == 0.5

    def test_two_hops_away(self):
        b = ContextBudgetManager()
        graph = CallGraph(
            nodes={"a.py", "b.py", "c.py"},
            edges=[
                GraphEdge(source_file="a.py", target_file="b.py", symbol_name="x"),
                GraphEdge(source_file="b.py", target_file="c.py", symbol_name="y"),
            ],
        )
        sym = Symbol(name="z", kind="function", file_path="c.py", line_number=1)
        score = b._graph_proximity(sym, ["a.py"], graph)
        assert score > 0.2


class TestRecencyWeight:
    def test_existing_file_has_positive_recency(self, tmp_path):
        b = ContextBudgetManager()
        f = tmp_path / "test.py"
        f.write_text("# test")
        score = b._recency_weight("test.py", str(tmp_path))
        assert score > 0.0

    def test_nonexistent_file_is_default(self):
        b = ContextBudgetManager()
        score = b._recency_weight("nonexistent/file.py", ".")
        assert score == 0.5


class TestBugDensity:
    def test_no_analyzer_is_default(self):
        b = ContextBudgetManager()
        score = b._historical_bug_density("src/file.py", None, ".")
        assert score == 0.5


class TestSymbolRanking:
    def test_returns_all_symbols(self):
        b = ContextBudgetManager()
        syms = [
            Symbol(name="f1", kind="function", file_path="a.py", line_number=1),
            Symbol(name="f2", kind="function", file_path="b.py", line_number=1),
        ]
        ranked = b.rank_symbols(syms, "test issue", ["a.py"])
        assert len(ranked) == 2

    def test_sorted_descending_by_relevance(self):
        b = ContextBudgetManager()
        syms = [
            Symbol(name="f1", kind="function", file_path="a.py", line_number=1),
            Symbol(name="f2", kind="function", file_path="b.py", line_number=1),
            Symbol(name="f3", kind="function", file_path="c.py", line_number=1),
        ]
        ranked = b.rank_symbols(syms, "f2 related stuff", ["b.py"])
        scores = [r.relevance for r in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_touched_file_scores_higher(self):
        b = ContextBudgetManager()
        syms = [
            Symbol(name="helper", kind="function", file_path="src/utils.py", line_number=1),
            Symbol(name="login", kind="function", file_path="src/auth.py", line_number=1),
        ]
        ranked = b.rank_symbols(syms, "fix the login auth bug", ["src/auth.py"])
        assert ranked[0].symbol.file_path == "src/auth.py"

    def test_empty_symbols_returns_empty(self):
        b = ContextBudgetManager()
        ranked = b.rank_symbols([], "test", [])
        assert ranked == []

    def test_relevance_weights_sum_to_one(self):
        total = sum(RELEVANCE_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001


class TestBudgetAssembly:
    def test_mock_model_assembly_produces_messages(self):
        b = ContextBudgetManager(model_name="mock")
        syms = [
            Symbol(name="f1", kind="function", file_path="a.py", line_number=1),
        ]
        result = b.assemble_context(
            "Fix the bug", syms, "Fix the bug",
            ["a.py"], ["convention: use logging"],
            repo_path=".",
        )
        assert isinstance(result, BudgetAssembly)
        assert len(result.messages) == 2
        assert result.messages[0]["role"] == "system"
        assert result.messages[1]["role"] == "user"
        assert result.total_tokens_used <= result.budget_limit
        assert result.headroom_remaining >= 0

    def test_assembly_includes_ranked_symbols(self):
        b = ContextBudgetManager(model_name="claude-3-5-sonnet-20241022")
        syms = [
            Symbol(name="calculate_total", kind="function", file_path="src/billing.py", line_number=10, docstring="Calculate the total price"),
            Symbol(name="validate_user", kind="function", file_path="src/auth.py", line_number=20, docstring="Validate user credentials"),
        ]
        result = b.assemble_context(
            "Fix price calculation", syms, "Fix price calculation",
            ["src/billing.py"], [],
            repo_path=".",
        )
        assert len(result.ranked_symbols) == 2

    def test_truncated_count_increases_on_tight_budget(self):
        b = ContextBudgetManager(model_name="mock")
        syms = [
            Symbol(name=f"sym_{i}", kind="function", file_path=f"file_{i}.py", line_number=1,
                   docstring="x" * 500)
            for i in range(100)
        ]
        result = b.assemble_context(
            "Fix the bug " * 50, syms, "Fix the bug " * 50,
            ["file_0.py"], [],
            repo_path=".",
        )
        assert result.truncated_count > 0

    def test_no_symbols_produces_empty_assembly(self):
        b = ContextBudgetManager()
        result = b.assemble_context(
            "Fix", [], "Fix", [], [],
            repo_path=".",
        )
        assert len(result.ranked_symbols) == 0
        assert result.truncated_count == 0

    def test_headroom_present_with_small_input(self):
        b = ContextBudgetManager(model_name="claude-3-5-sonnet-20241022")
        result = b.assemble_context(
            "Fix", [], "Fix", [], [],
            repo_path=".",
        )
        assert result.headroom_remaining > 0

    def test_headroom_zero_with_large_input(self):
        b = ContextBudgetManager(model_name="mock")
        syms = [
            Symbol(name=f"sym_{i}", kind="function", file_path=f"file_{i}.py", line_number=1)
            for i in range(30)
        ]
        result = b.assemble_context(
            "Fix the bug " * 200, syms, "Fix the bug " * 200,
            ["file_0.py"], ["memory " * 50],
            repo_path=".",
        )
        assert result.headroom_remaining >= 0

    def test_backward_compat_assemble_context_simple(self):
        b = ContextBudgetManager(model_name="mock")
        messages = b.assemble_context_simple(
            "Fix bug",
            {"a.py": "x = 1"},
            ["use pydantic"],
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"


class TestRankedSymbolTruncation:
    def test_truncated_flag_set_on_budget_exhausted(self):
        b = ContextBudgetManager(model_name="mock")
        syms = [
            Symbol(name=f"f{i}", kind="function", file_path=f"f{i}.py", line_number=1,
                   docstring="x" * 400)
            for i in range(100)
        ]
        result = b.assemble_context(
            "fix " * 200, syms, "fix " * 200, ["f0.py"], [],
            repo_path=".",
        )
        truncated = [rs for rs in result.ranked_symbols if rs.context_truncated]
        assert len(truncated) > 0
        for t in truncated:
            assert t.truncated_reason in ("budget_exhausted", "body_omitted_budget")

    def test_no_truncation_when_budget_plentiful(self):
        b = ContextBudgetManager(model_name="claude-3-5-sonnet-20241022")
        syms = [
            Symbol(name="f1", kind="function", file_path="f1.py", line_number=1),
        ]
        result = b.assemble_context(
            "fix", syms, "fix", ["f1.py"], [],
            repo_path=".",
        )
        truncated = [rs for rs in result.ranked_symbols if rs.context_truncated]
        assert len(truncated) == 0
