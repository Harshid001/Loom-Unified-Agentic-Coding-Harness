from typing import Any, Dict

from loom.orchestrator.agents.base_agent import BaseAgent
from loom.orchestrator.state import OrchestratorState
from loom.repo_intel.cache import RepoIntelCache
from loom.repo_intel.call_graph import CallGraphBuilder
from loom.repo_intel.mapper import RepoMapper
from loom.repo_intel.parser import SymbolParser


class OnboardingAgent(BaseAgent):
    """Scans repository structure, parses symbols, builds call graph, and maps test entry points using cached repo intel."""

    async def execute(self, state: OrchestratorState) -> Dict[str, Any]:
        mapper = RepoMapper()
        repo_map = RepoIntelCache.get_repo_map(state.repo_path, mapper)

        parser = SymbolParser()
        symbols = RepoIntelCache.get_symbols(state.repo_path, parser, repo_map.file_tree)

        builder = CallGraphBuilder()
        call_graph = builder.build_graph(symbols)


        onboarding_summary = {
            "total_files": repo_map.total_files,
            "languages": repo_map.languages,
            "build_systems": repo_map.build_system,
            "test_frameworks": repo_map.test_frameworks,
            "symbols_count": len(symbols),
            "graph_nodes": len(call_graph.nodes),
            "key_files": repo_map.key_files
        }

        state.shared_data["repo_map"] = repo_map.model_dump()
        state.shared_data["onboarding_summary"] = onboarding_summary
        return onboarding_summary
