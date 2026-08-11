import os
from pathlib import Path
from typing import Dict, List

from pydantic import BaseModel, Field


class LanguageInfo(BaseModel):
    name: str
    file_count: int = 0
    extensions: List[str] = Field(default_factory=list)


class RepoMap(BaseModel):
    root_path: str
    total_files: int = 0
    languages: Dict[str, int] = Field(default_factory=dict)
    build_system: List[str] = Field(default_factory=list)
    test_frameworks: List[str] = Field(default_factory=list)
    key_files: List[str] = Field(default_factory=list)
    file_tree: List[str] = Field(default_factory=list)


class RepoMapper:
    """Scans repository structure, languages, build setup, and test entry points."""

    IGNORE_DIRS = {
        ".git",
        ".venv",
        "node_modules",
        "__pycache__",
        ".pytest_cache",
        "dist",
        "build",
        ".next",
        ".cache",
        "target",
        "vendor",
        ".gemini",
    }

    BUILD_INDICATORS = {
        "pyproject.toml": ("Python", "pip/uv"),
        "setup.py": ("Python", "setuptools"),
        "package.json": ("JavaScript/TypeScript", "npm"),
        "Cargo.toml": ("Rust", "cargo"),
        "go.mod": ("Go", "go modules"),
        "pom.xml": ("Java", "maven"),
        "build.gradle": ("Java/Kotlin", "gradle"),
        "Makefile": ("Polyglot", "make"),
    }

    TEST_INDICATORS = {
        "pytest.ini": "pytest",
        "conftest.py": "pytest",
        "jest.config.js": "jest",
        "jest.config.ts": "jest",
        "vitest.config.ts": "vitest",
    }

    EXT_MAP = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".h": "C/C++",
        ".md": "Markdown",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
    }

    def map_repository(self, repo_path: str, max_depth: int = 4) -> RepoMap:
        path = Path(repo_path).resolve()
        if not path.exists() or not path.is_dir():
            raise ValueError(f"Invalid repository path: {repo_path}")

        total_files = 0
        languages: Dict[str, int] = {}
        build_systems = set()
        test_frameworks = set()
        key_files = []
        file_tree = []

        for root, dirs, files in os.walk(path):
            dirs[:] = [d for d in dirs if d not in self.IGNORE_DIRS]
            rel_root = Path(root).relative_to(path)
            depth = len(rel_root.parts)

            if depth > max_depth:
                continue

            for file_name in files:
                rel_file_path = str(rel_root / file_name) if str(rel_root) != "." else file_name
                file_tree.append(rel_file_path)
                total_files += 1

                # Check build & test indicators
                if file_name in self.BUILD_INDICATORS:
                    lang, bsys = self.BUILD_INDICATORS[file_name]
                    build_systems.add(bsys)
                    key_files.append(rel_file_path)

                if file_name in self.TEST_INDICATORS:
                    test_frameworks.add(self.TEST_INDICATORS[file_name])
                    key_files.append(rel_file_path)

                # Check language extension
                ext = Path(file_name).suffix.lower()
                if ext in self.EXT_MAP:
                    lang = self.EXT_MAP[ext]
                    languages[lang] = languages.get(lang, 0) + 1

        # Heuristic detection for tests if no config file was found
        if not test_frameworks:
            if "Python" in languages:
                test_frameworks.add("pytest")
            elif "JavaScript" in languages or "TypeScript" in languages:
                test_frameworks.add("npm test")
            elif "Go" in languages:
                test_frameworks.add("go test")
            elif "Rust" in languages:
                test_frameworks.add("cargo test")

        return RepoMap(
            root_path=str(path),
            total_files=total_files,
            languages=languages,
            build_system=sorted(list(build_systems)),
            test_frameworks=sorted(list(test_frameworks)),
            key_files=sorted(key_files),
            file_tree=file_tree[:300],
        )
