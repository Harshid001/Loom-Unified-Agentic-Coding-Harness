from loom.repo_intel.cache import RepoIntelCache
from loom.repo_intel.mapper import RepoMapper
from loom.repo_intel.parser import SymbolParser


def test_repo_intel_cache(tmp_path):
    RepoIntelCache.clear()

    # Create test python file in tmp_path
    py_file = tmp_path / "sample.py"
    py_file.write_text("def hello():\n    return 'world'\n", encoding="utf-8")

    mapper = RepoMapper()
    parser = SymbolParser()

    map1 = RepoIntelCache.get_repo_map(str(tmp_path), mapper)
    syms1 = RepoIntelCache.get_symbols(str(tmp_path), parser, map1.file_tree)

    # Fetch again - should return cached instance
    map2 = RepoIntelCache.get_repo_map(str(tmp_path), mapper)
    syms2 = RepoIntelCache.get_symbols(str(tmp_path), parser, map2.file_tree)

    assert map1 == map2
    assert syms1 == syms2

    # Clear cache
    RepoIntelCache.clear()
