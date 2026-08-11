from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field

from loom.repo_intel.mapper import RepoMap, RepoMapper


class SubProject(BaseModel):
    name: str
    path: str
    repo_map: Optional[RepoMap] = None
    build_system: str = ""
    test_frameworks: List[str] = Field(default_factory=list)
    depends_on: List[str] = Field(default_factory=list)
    is_service: bool = False


class MonorepoConfig(BaseModel):
    root_path: str
    sub_projects: List[SubProject] = Field(default_factory=list)
    shared_packages: List[str] = Field(default_factory=list)
    build_order: List[str] = Field(default_factory=list)


class MonorepoScanner:
    """Detects and maps monorepo structures with multiple sub-projects."""

    MONOREPO_INDICATORS = {
        "pnpm-workspace.yaml",
        "lerna.json",
        "nx.json",
        "turbo.json",
        "rush.json",
        ".monorepo",
        "workspace.yaml",
    }

    SUBPROJECT_INDICATORS = {
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "pom.xml",
        "build.gradle",
        "Makefile",
    }

    @classmethod
    def is_monorepo(cls, repo_path: str) -> bool:
        root = Path(repo_path)
        for indicator in cls.MONOREPO_INDICATORS:
            if (root / indicator).exists():
                return True

        subproject_count = 0
        for item in root.iterdir():
            if item.is_dir() and not item.name.startswith(".") and item.name != "node_modules":
                for indicator in cls.SUBPROJECT_INDICATORS:
                    if (item / indicator).exists():
                        subproject_count += 1
                        break
        return subproject_count >= 2

    @classmethod
    def scan_monorepo(cls, repo_path: str) -> MonorepoConfig:
        root = Path(repo_path).resolve()
        mapper = RepoMapper()
        config = MonorepoConfig(root_path=str(root))

        for item in sorted(root.iterdir()):
            if not item.is_dir() or item.name.startswith(".") or item.name in ("node_modules", "__pycache__", ".git"):
                continue

            for indicator in cls.SUBPROJECT_INDICATORS:
                if (item / indicator).exists():
                    sp = SubProject(name=item.name, path=str(item))
                    try:
                        sp.repo_map = mapper.map_repository(str(item), max_depth=3)
                        sp.build_system = ", ".join(sp.repo_map.build_system)
                        sp.test_frameworks = sp.repo_map.test_frameworks
                    except Exception:
                        sp.build_system = "unknown"
                    config.sub_projects.append(sp)

                    if any(d in item.name.lower() for d in ("service", "api", "server", "worker")):
                        sp.is_service = True
                    break

        for sp in config.sub_projects:
            if sp.repo_map:
                deps = cls._detect_dependencies(sp, config.sub_projects)
                sp.depends_on = deps

        config.shared_packages = [
            sp.name
            for sp in config.sub_projects
            if any(k in sp.name.lower() for k in ("common", "shared", "lib", "util", "core", "base"))
        ]

        config.build_order = cls._compute_build_order(config.sub_projects)

        return config

    @classmethod
    def _detect_dependencies(cls, project: SubProject, all_projects: List[SubProject]) -> List[str]:
        deps = []
        proj_path = Path(project.path)

        for dep_file in ["requirements.txt", "pyproject.toml", "package.json", "Cargo.toml", "go.mod"]:
            dep_path = proj_path / dep_file
            if not dep_path.exists():
                continue
            try:
                content = dep_path.read_text(encoding="utf-8", errors="ignore")
                for other in all_projects:
                    if other.name != project.name and other.name in content:
                        deps.append(other.name)
            except Exception:
                pass

        return deps

    @classmethod
    def _compute_build_order(cls, projects: List[SubProject]) -> List[str]:
        visited = set()
        order = []

        def visit(name: str):
            if name in visited:
                return
            visited.add(name)
            for sp in projects:
                if sp.name == name:
                    for dep in sp.depends_on:
                        visit(dep)
                    order.append(name)
                    return

        for sp in projects:
            visit(sp.name)

        return order
