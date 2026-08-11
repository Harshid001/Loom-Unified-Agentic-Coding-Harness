from loom.repo_intel.mapper import RepoMapper
from loom.repo_intel.parser import SymbolParser


def test_repo_mapper(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='test'\n", encoding="utf-8")
    (tmp_path / "main.py").write_text("def hello(): pass\n", encoding="utf-8")

    mapper = RepoMapper()
    repo_map = mapper.map_repository(str(tmp_path))
    assert repo_map.total_files == 2
    assert "Python" in repo_map.languages


def test_symbol_parser(tmp_path):
    sample_code = """
class Calculator:
    def add(self, a, b):
        return a + b
"""
    file_path = tmp_path / "calc.py"
    file_path.write_text(sample_code, encoding="utf-8")

    parser = SymbolParser()
    symbols = parser.parse_file(str(file_path), str(tmp_path))
    assert any(s.name == "Calculator" and s.kind == "class" for s in symbols)
    assert any(s.name == "add" and s.kind == "method" for s in symbols)
