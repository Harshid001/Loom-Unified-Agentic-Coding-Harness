import ast
import re
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel


class Symbol(BaseModel):
    name: str
    kind: str  # "function", "class", "method", "import"
    file_path: str
    line_number: int
    docstring: Optional[str] = None
    parent_symbol: Optional[str] = None


class SymbolParser:
    """Extracts symbols, classes, functions, and imports from code files."""

    def parse_file(self, file_path: str, repo_root: str) -> List[Symbol]:
        path = Path(file_path)
        if not path.is_file():
            return []

        rel_path = str(path.relative_to(Path(repo_root))) if path.is_relative_to(Path(repo_root)) else str(path)
        ext = path.suffix.lower()

        if ext == ".py":
            return self._parse_python(path, rel_path)
        else:
            return self._parse_generic_regex(path, rel_path)

    def _parse_python(self, path: Path, rel_path: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        try:
            content = path.read_text(encoding="utf-8", errors="ignore")
            tree = ast.parse(content, filename=str(path))

            for node in ast.walk(tree):
                if isinstance(node, ast.ClassDef):
                    symbols.append(
                        Symbol(
                            name=node.name,
                            kind="class",
                            file_path=rel_path,
                            line_number=node.lineno,
                            docstring=ast.get_docstring(node),
                        )
                    )
                    for item in node.body:
                        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            symbols.append(
                                Symbol(
                                    name=item.name,
                                    kind="method",
                                    file_path=rel_path,
                                    line_number=item.lineno,
                                    docstring=ast.get_docstring(item),
                                    parent_symbol=node.name,
                                )
                            )
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    # Only top-level functions (not methods inside classes)
                    symbols.append(
                        Symbol(
                            name=node.name,
                            kind="function",
                            file_path=rel_path,
                            line_number=node.lineno,
                            docstring=ast.get_docstring(node),
                        )
                    )
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        symbols.append(
                            Symbol(name=alias.name, kind="import", file_path=rel_path, line_number=node.lineno)
                        )
                elif isinstance(node, ast.ImportFrom):
                    module = node.module or ""
                    for alias in node.names:
                        symbols.append(
                            Symbol(
                                name=f"{module}.{alias.name}" if module else alias.name,
                                kind="import",
                                file_path=rel_path,
                                line_number=node.lineno,
                            )
                        )
        except Exception:
            # Fallback regex if AST parsing fails
            symbols.extend(self._parse_generic_regex(path, rel_path))

        return symbols

    def _parse_generic_regex(self, path: Path, rel_path: str) -> List[Symbol]:
        symbols: List[Symbol] = []
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
            fn_pattern = re.compile(r"^\s*(async\s+)?(def|function|func|fn|pub fn)\s+([a-zA-Z0-9_]+)")
            cls_pattern = re.compile(r"^\s*(class|struct|interface|type)\s+([a-zA-Z0-9_]+)")

            for idx, line in enumerate(lines, start=1):
                fn_match = fn_pattern.search(line)
                if fn_match:
                    symbols.append(Symbol(name=fn_match.group(3), kind="function", file_path=rel_path, line_number=idx))
                    continue

                cls_match = cls_pattern.search(line)
                if cls_match:
                    symbols.append(Symbol(name=cls_match.group(2), kind="class", file_path=rel_path, line_number=idx))
        except Exception:
            pass

        return symbols
