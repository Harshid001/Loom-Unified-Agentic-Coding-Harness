import hashlib
import os
from pathlib import Path
from typing import Any, Dict, List, Tuple, cast

from loom.repo_intel.mapper import RepoMap, RepoMapper
from loom.repo_intel.parser import Symbol, SymbolParser


class RepoIntelCache:
    """Caching layer for repository intelligence (repo map and AST symbol parsing) with fingerprint invalidation."""

    _cache_store: Dict[str, Tuple[str, Any]] = {}

    @classmethod
    def get_fingerprint(cls, repo_path: str) -> str:
        path = Path(repo_path).resolve()
        if not path.exists():
            return ""

        # Try git commit hash if .git directory exists
        git_dir = path / ".git"
        if git_dir.exists():
            try:
                head_file = git_dir / "HEAD"
                if head_file.exists():
                    ref = head_file.read_text(encoding="utf-8").strip()
                    if ref.startswith("ref: "):
                        target = git_dir / ref.split(" ")[1]
                        if target.exists():
                            return target.read_text(encoding="utf-8").strip()
            except Exception:
                pass

        # Fallback to mtime/size hash of top 200 files
        hasher = hashlib.sha256()
        count = 0
        for root, _, files in os.walk(path):
            if ".git" in root or "node_modules" in root or "__pycache__" in root:
                continue
            for f in sorted(files):
                full_path = Path(root) / f
                try:
                    stat = full_path.stat()
                    hasher.update(f"{f}:{stat.st_mtime}:{stat.st_size}".encode("utf-8"))
                    count += 1
                except Exception:
                    pass
            if count > 200:
                break

        return hasher.hexdigest()

    @classmethod
    def get_repo_map(cls, repo_path: str, mapper: RepoMapper) -> RepoMap:
        fp = cls.get_fingerprint(repo_path)
        cache_key = f"repo_map:{Path(repo_path).resolve()}"
        if cache_key in cls._cache_store:
            cached_fp, cached_map = cls._cache_store[cache_key]
            if cached_fp == fp:
                return cast(RepoMap, cached_map)

        repo_map = mapper.map_repository(repo_path)
        cls._cache_store[cache_key] = (fp, repo_map)
        return repo_map

    @classmethod
    def get_symbols(cls, repo_path: str, parser: SymbolParser, file_tree: List[str]) -> List[Symbol]:

        fp = cls.get_fingerprint(repo_path)
        cache_key = f"symbols:{Path(repo_path).resolve()}"
        if cache_key in cls._cache_store:
            cached_fp, cached_syms = cls._cache_store[cache_key]
            if cached_fp == fp:
                return cast(List[Symbol], cached_syms)

        symbols = []
        for file_path in file_tree[:50]:
            full_path = f"{repo_path}/{file_path}"
            syms = parser.parse_file(full_path, repo_path)
            symbols.extend(syms)

        cls._cache_store[cache_key] = (fp, symbols)
        return symbols

    @classmethod
    def clear(cls):
        cls._cache_store.clear()
