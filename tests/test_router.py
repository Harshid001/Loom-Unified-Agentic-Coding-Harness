import pytest

from loom.adapters.router import (
    ModelRouter,
    RouterEventType,
    TaskType,
)


class TestModelScoring:
    def test_all_eligible_models_score_positive(self):
        router = ModelRouter(mock_mode=True)
        for model in router._eligible_models:
            score = router.score_model(model, TaskType.PATCHING)
            assert score >= 0, f"{model} should have non-negative score"

    def test_deepseek_scores_higher_than_opus_on_cost(self):
        router = ModelRouter(mock_mode=True)
        router.set_eligible_models(["deepseek-v3", "claude-3-opus-20240229"])
        ds_score = router.score_model("deepseek-v3", TaskType.ONBOARDING)
        opus_score = router.score_model("claude-3-opus-20240229", TaskType.ONBOARDING)
        assert ds_score > opus_score, "deepseek-v3 should outscore opus on cost basis"

    def test_gpt4o_mini_scores_low_on_capability_for_patching(self):
        router = ModelRouter(mock_mode=True)
        mini_cap = router._capability_match("gpt-4o-mini", TaskType.PATCHING)
        opus_cap = router._capability_match("claude-3-opus-20240229", TaskType.PATCHING)
        assert mini_cap < opus_cap

    def test_rank_models_excludes_provided_list(self):
        router = ModelRouter(mock_mode=True)
        ranked = router.rank_models(TaskType.REVIEWING, excluded=["gpt-4o-mini"])
        models = [m for m, _ in ranked]
        assert "gpt-4o-mini" not in models

    def test_rank_models_returns_sorted_descending(self):
        router = ModelRouter(mock_mode=True)
        ranked = router.rank_models(TaskType.PATCHING)
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True)

    def test_select_model_picks_highest_scoring(self):
        router = ModelRouter(mock_mode=True)
        selected = router.select_model(TaskType.ONBOARDING)
        ranked = router.rank_models(TaskType.ONBOARDING)
        assert selected == ranked[0][0]

    def test_select_model_excludes_failed_models(self):
        router = ModelRouter(mock_mode=True)
        top_model = router.rank_models(TaskType.PATCHING)[0][0]
        selected = router.select_model(TaskType.PATCHING, excluded=[top_model])
        assert selected != top_model

    def test_select_model_returns_default_when_all_excluded(self):
        router = ModelRouter(mock_mode=True)
        all_models = list(router._eligible_models)
        selected = router.select_model(TaskType.PATCHING, excluded=all_models)
        assert selected == router.default_model

    def test_quota_headroom_zero_blocks_model(self):
        router = ModelRouter(mock_mode=True)
        top = router.rank_models(TaskType.PATCHING)[0][0]
        router.set_quota_headroom(top, 0)
        selected = router.select_model(TaskType.PATCHING)
        assert selected != top

    def test_quota_headroom_positive_allows_model(self):
        router = ModelRouter(mock_mode=True)
        top = router.rank_models(TaskType.PATCHING)[0][0]
        router.set_quota_headroom(top, 10_000_000)
        selected = router.select_model(TaskType.PATCHING)
        assert selected == top

    def test_mock_mode_always_returns_mock(self):
        router = ModelRouter(mock_mode=True)
        for task in TaskType:
            assert router.resolve_model(task.value) == "mock"

    def test_custom_weights_affect_scoring(self):
        router_cost = ModelRouter(
            mock_mode=True,
            weights={"w1_cost": 0.90, "w2_latency": 0.05, "w3_success_rate": 0.03, "w4_capability": 0.02},
        )
        router_latency = ModelRouter(
            mock_mode=True,
            weights={"w1_cost": 0.02, "w2_latency": 0.90, "w3_success_rate": 0.05, "w4_capability": 0.03},
        )
        router_cost.set_eligible_models(["deepseek-v3", "claude-3-opus-20240229"])
        router_latency.set_eligible_models(["deepseek-v3", "claude-3-opus-20240229"])

        cost_select = router_cost.select_model(TaskType.PATCHING)
        assert cost_select == "deepseek-v3"


class TestProviderHealth:
    def test_unhealthy_provider_scores_zero(self):
        router = ModelRouter(mock_mode=True)
        for _ in range(5):
            router.record_event("gpt-4o-mini", TaskType.PATCHING, RouterEventType.FAILURE, 500)
        assert router._is_provider_unhealthy("gpt-4o-mini")
        score = router.score_model("gpt-4o-mini", TaskType.PATCHING)
        assert score == 0.0

    def test_healthy_provider_scores_positive(self):
        router = ModelRouter(mock_mode=True)
        for _ in range(10):
            router.record_event("gpt-4o-mini", TaskType.PATCHING, RouterEventType.SUCCESS, 300)
        assert not router._is_provider_unhealthy("gpt-4o-mini")
        score = router.score_model("gpt-4o-mini", TaskType.PATCHING)
        assert score > 0.0

    def test_mixed_events_below_threshold_stays_healthy(self):
        router = ModelRouter(mock_mode=True)
        for _ in range(9):
            router.record_event("deepseek-v3", TaskType.REPRODUCTION, RouterEventType.SUCCESS, 200)
        router.record_event("deepseek-v3", TaskType.REPRODUCTION, RouterEventType.FAILURE, 200)
        assert not router._is_provider_unhealthy("deepseek-v3")

    def test_mixed_events_above_threshold_becomes_unhealthy(self):
        router = ModelRouter(mock_mode=True)
        for _ in range(5):
            router.record_event("deepseek-v3", TaskType.REPRODUCTION, RouterEventType.SUCCESS, 200)
        for _ in range(5):
            router.record_event("deepseek-v3", TaskType.REPRODUCTION, RouterEventType.FAILURE, 200)
        assert router._is_provider_unhealthy("deepseek-v3")

    def test_no_events_yields_zero_error_rate(self):
        router = ModelRouter(mock_mode=True)
        assert router._provider_error_rate("nonexistent-model") == 0.0
        assert not router._is_provider_unhealthy("nonexistent-model")


class TestFallbackCascade:
    def test_cascade_contains_up_to_three_models(self):
        router = ModelRouter(mock_mode=True)
        cascade = router.build_fallback_cascade(TaskType.PATCHING)
        assert 1 <= len(cascade) <= 3

    def test_cascade_excludes_unhealthy_models(self):
        router = ModelRouter(mock_mode=True)
        top = router.rank_models(TaskType.PATCHING)[0][0]
        for _ in range(10):
            router.record_event(top, TaskType.PATCHING, RouterEventType.FAILURE, 500)
        cascade = router.build_fallback_cascade(TaskType.PATCHING)
        assert top not in cascade

    def test_cascade_sorted_by_score_descending(self):
        router = ModelRouter(mock_mode=True)
        cascade = router.build_fallback_cascade(TaskType.ONBOARDING)
        scores = [router.score_model(m, TaskType.ONBOARDING) for m in cascade]
        assert scores == sorted(scores, reverse=True)

    def test_cascade_defaults_to_default_model_when_all_unhealthy(self):
        router = ModelRouter(mock_mode=True)
        for model in router._eligible_models:
            for _ in range(10):
                router.record_event(model, TaskType.PATCHING, RouterEventType.FAILURE, 500)
        cascade = router.build_fallback_cascade(TaskType.PATCHING)
        assert router.default_model in cascade


class TestPatchRiskClassification:
    def test_auth_path_is_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.classify_patch_risk(5, ["src/auth/login.ts"])

    def test_billing_path_is_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.classify_patch_risk(10, ["backend/billing/invoice.py"])

    def test_migrations_path_is_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.classify_patch_risk(20, ["db/migrations/042_add_column.sql"])

    def test_large_diff_is_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.classify_patch_risk(200, ["src/utils.py"])

    def test_small_diff_non_sensitive_is_low_risk(self):
        router = ModelRouter(mock_mode=True)
        assert not router.classify_patch_risk(10, ["src/utils.py"])

    def test_low_confidence_is_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.classify_patch_risk(10, ["src/utils.py"], prior_confidence=0.5)

    def test_high_confidence_non_sensitive_is_low_risk(self):
        router = ModelRouter(mock_mode=True)
        assert not router.classify_patch_risk(10, ["src/utils.py"], prior_confidence=0.85)

    def test_custom_sensitive_globs(self):
        router = ModelRouter(mock_mode=True, sensitive_globs=["**/secret/**"])
        assert router.classify_patch_risk(5, ["src/secret/keys.py"])
        assert not router.classify_patch_risk(5, ["src/public/utils.py"])


class TestConsensusVerification:
    def test_needs_consensus_always_on(self):
        router = ModelRouter(mock_mode=True)
        assert router.needs_consensus("diff", ["src/utils.py"], consensus_mode="always-on")

    def test_needs_consensus_off(self):
        router = ModelRouter(mock_mode=True)
        assert not router.needs_consensus("diff", ["src/utils.py"], consensus_mode="off")

    def test_needs_consensus_auto_high_risk(self):
        router = ModelRouter(mock_mode=True)
        assert router.needs_consensus("diff", ["src/auth/login.ts"])

    def test_needs_consensus_auto_low_risk(self):
        router = ModelRouter(mock_mode=True)
        assert not router.needs_consensus("diff", ["src/utils.py"])

    @pytest.mark.asyncio
    async def test_verify_consensus_passes_with_two_agreements(self):
        router = ModelRouter(mock_mode=True)
        patch1 = "+x = 1\n+y = 2"
        patch2 = "+x = 1\n+y = 2\n+z = 3"
        patch3 = "+x = 1\n+y = 2"
        result = await router.verify_consensus([patch1, patch2, patch3], required_agreement=2)
        assert result.passed

    @pytest.mark.asyncio
    async def test_verify_consensus_fails_with_no_agreement(self):
        router = ModelRouter(mock_mode=True)
        result = await router.verify_consensus(
            ["+foo = bar", "+baz = qux", "+hello = world"],
            required_agreement=2,
        )
        assert not result.passed

    @pytest.mark.asyncio
    async def test_verify_consensus_single_patch_passes_with_required_one(self):
        router = ModelRouter(mock_mode=True)
        result = await router.verify_consensus(["+x = 1"], required_agreement=1)
        assert result.passed

    @pytest.mark.asyncio
    async def test_verify_consensus_fails_with_single_patch_required_two(self):
        router = ModelRouter(mock_mode=True)
        result = await router.verify_consensus(["+x = 1"], required_agreement=2)
        assert not result.passed

    @pytest.mark.asyncio
    async def test_verify_consensus_handles_empty_list(self):
        router = ModelRouter(mock_mode=True)
        result = await router.verify_consensus([], required_agreement=2)
        assert not result.passed

    def test_patch_intent_extraction_normalizes_diff(self):
        router = ModelRouter(mock_mode=True)
        diff = """--- a/file.py
+++ b/file.py
@@ -1,3 +1,4 @@
-x = 1
+x = 2
+y = 3
 z = 4"""
        intent = router._extract_patch_intent(diff)
        assert "x = 2" in intent
        assert "y = 3" in intent
        assert "z = 4" not in intent

    def test_patch_intent_truncates_long_content(self):
        router = ModelRouter(mock_mode=True)
        long_diff = "+" + "a" * 600
        intent = router._extract_patch_intent(long_diff)
        assert len(intent) <= 500

    def test_intents_similar_jaccard_threshold(self):
        router = ModelRouter(mock_mode=True)
        assert router._intents_similar("add user validation", "add user input validation")
        assert not router._intents_similar("add user validation", "fix database migration")
        assert not router._intents_similar("", "something")

    def test_empty_intent_comparison(self):
        router = ModelRouter(mock_mode=True)
        assert not router._intents_similar("", "")
        assert not router._intents_similar("   ", "something")


class TestCostEstimation:
    def test_known_model_cost(self):
        router = ModelRouter(mock_mode=True)
        cost = router.estimate_cost("gpt-4o", 1000, 500)
        expected = (1000 * 2.50 / 1e6) + (500 * 10.00 / 1e6)
        assert abs(cost - expected) < 1e-10

    def test_unknown_model_falls_back_to_claude(self):
        router = ModelRouter(mock_mode=True)
        cost = router.estimate_cost("unknown-model", 1000, 500)
        expected = (1000 * 3.00 / 1e6) + (500 * 15.00 / 1e6)
        assert abs(cost - expected) < 1e-10

    def test_mock_model_cost(self):
        router = ModelRouter(mock_mode=True)
        cost = router.estimate_cost("mock", 1000, 500)
        expected = (1000 * 0.001 / 1e6) + (500 * 0.002 / 1e6)
        assert abs(cost - expected) < 1e-10


class TestExplicitModelVsAutoRouting:
    def test_explicit_model_selection_used_across_all_nodes(self):
        router = ModelRouter(default_model="gpt-4o", mock_mode=False)
        for node in ["onboarding", "reproduction", "planner", "patcher", "verifier", "reviewer"]:
            assert router.resolve_model(node) == "gpt-4o"

    def test_set_model_updates_explicit_execution(self):
        router = ModelRouter(default_model="gpt-4o", mock_mode=False)
        router.set_model("gemini-3-flash-preview")
        assert router.default_model == "gemini-3-flash-preview"
        assert "gemini-3-flash-preview" in router._eligible_models
        for node in ["onboarding", "reproduction", "planner", "patcher", "verifier", "reviewer"]:
            assert router.resolve_model(node) == "gemini-3-flash-preview"

    def test_auto_routing_mode_performs_dynamic_scoring(self):
        router = ModelRouter(default_model="auto", mock_mode=False)
        assert router.auto_route is True
        for node in ["onboarding", "reproduction", "planner", "patcher", "verifier", "reviewer"]:
            selected = router.resolve_model(node)
            assert selected in router._eligible_models
            assert selected != "auto"

    def test_auto_route_flag_overrides_explicit_default(self):
        router = ModelRouter(default_model="gpt-4o", auto_route=True, mock_mode=False)
        assert router.auto_route is True
        selected = router.resolve_model("patcher")
        assert selected in router._eligible_models

