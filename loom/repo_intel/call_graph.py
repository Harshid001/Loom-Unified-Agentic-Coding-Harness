from typing import Dict, List, Set

from pydantic import BaseModel, Field

from loom.repo_intel.parser import Symbol


class GraphEdge(BaseModel):
    source_file: str
    target_file: str
    symbol_name: str
    weight: int = 1

class CallGraph(BaseModel):
    nodes: Set[str] = Field(default_factory=set)
    edges: List[GraphEdge] = Field(default_factory=list)
    symbol_index: Dict[str, List[Symbol]] = Field(default_factory=dict)

class CallGraphBuilder:
    """Builds import and invocation dependencies between files in the repository."""

    def build_graph(self, symbols: List[Symbol]) -> CallGraph:
        graph = CallGraph()
        symbol_map: Dict[str, List[Symbol]] = {}

        for sym in symbols:
            graph.nodes.add(sym.file_path)
            symbol_map.setdefault(sym.name, []).append(sym)

        graph.symbol_index = symbol_map

        # Map import symbols to source files
        for sym in symbols:
            if sym.kind == "import":
                # Find matching target files
                target_syms = symbol_map.get(sym.name, [])
                for t in target_syms:
                    if t.file_path != sym.file_path:
                        graph.edges.append(GraphEdge(
                            source_file=sym.file_path,
                            target_file=t.file_path,
                            symbol_name=sym.name
                        ))

        return graph
