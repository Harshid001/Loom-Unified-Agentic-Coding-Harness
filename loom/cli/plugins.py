import importlib.util  # noqa: F401
import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

logger = logging.getLogger("loom.cli.plugins")


class HookContext(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: str
    node_name: str
    repo_path: str
    issue_description: str
    state_data: Dict[str, Any] = Field(default_factory=dict)


class PluginManifest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    name: str
    version: str
    description: str = ""
    author: str = ""
    hooks: List[str] = Field(default_factory=list)
    custom_agents: List[str] = Field(default_factory=list)


PreAgentHook = Callable[[HookContext], Optional[HookContext]]
PostAgentHook = Callable[[HookContext, Dict[str, Any]], Optional[Dict[str, Any]]]
CustomAgentFactory = Callable[[], Any]


class PluginRegistry:
    _instance: Optional["PluginRegistry"] = None
    _plugins: Dict[str, Any] = {}
    _pre_hooks: Dict[str, List[PreAgentHook]] = {}
    _post_hooks: Dict[str, List[PostAgentHook]] = {}
    _custom_agents: Dict[str, CustomAgentFactory] = {}
    _manifests: Dict[str, PluginManifest] = {}
    _plugin_dir: Optional[Path] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def discover_plugins(cls, plugin_dir: Optional[str] = None):
        if plugin_dir:
            cls._plugin_dir = Path(plugin_dir)
        else:
            cls._plugin_dir = Path.home() / ".loom" / "plugins"

        if not cls._plugin_dir.exists():
            cls._plugin_dir.mkdir(parents=True, exist_ok=True)

        for item in cls._plugin_dir.iterdir():
            if item.is_dir() and (item / "__init__.py").exists():
                cls._load_plugin_package(item)
            elif item.suffix == ".py" and not item.name.startswith("_"):
                cls._load_plugin_file(item)

    @classmethod
    def _load_plugin_package(cls, path: Path):
        try:
            spec = importlib.util.spec_from_file_location(path.name, str(path / "__init__.py"))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                cls._register_plugin_module(mod, path.name)
        except Exception as e:
            logger.warning("Failed to load plugin package %s: %s", path.name, e)

    @classmethod
    def _load_plugin_file(cls, path: Path):
        try:
            spec = importlib.util.spec_from_file_location(path.stem, str(path))
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                cls._register_plugin_module(mod, path.stem)
        except Exception as e:
            logger.warning("Failed to load plugin file %s: %s", path.name, e)

    @classmethod
    def _register_plugin_module(cls, mod: Any, name: str):
        manifest = getattr(mod, "PLUGIN_MANIFEST", None)
        if isinstance(manifest, dict):
            manifest = PluginManifest(**manifest)
        elif manifest is None:
            manifest = PluginManifest(name=name, version="0.1.0")

        cls._manifests[name] = manifest
        cls._plugins[name] = mod

        for hook_name in manifest.hooks:
            hook_func = getattr(mod, hook_name, None)
            if hook_func and callable(hook_func):
                cls.register_hook(hook_name, hook_func)

        for agent_name in manifest.custom_agents:
            agent_factory = getattr(mod, agent_name, None)
            if agent_factory and callable(agent_factory):
                cls._custom_agents[agent_name] = agent_factory

    @classmethod
    def register_hook(cls, hook_name: str, hook_func: Callable):
        if "pre_" in hook_name:
            node = hook_name.replace("pre_", "")
            cls._pre_hooks.setdefault(node, []).append(hook_func)
        elif "post_" in hook_name:
            node = hook_name.replace("post_", "")
            cls._post_hooks.setdefault(node, []).append(hook_func)
        else:
            cls._pre_hooks.setdefault(hook_name, []).append(hook_func)

    @classmethod
    def run_pre_hooks(cls, node_name: str, ctx: HookContext) -> HookContext:
        for hook in cls._pre_hooks.get(node_name, []):
            try:
                result = hook(ctx)
                if result is not None:
                    ctx = result
            except Exception as e:
                logger.warning("Pre-hook for %s failed: %s", node_name, e)
        return ctx

    @classmethod
    def run_post_hooks(cls, node_name: str, ctx: HookContext, output: Dict[str, Any]) -> Dict[str, Any]:
        for hook in cls._post_hooks.get(node_name, []):
            try:
                result = hook(ctx, output)
                if result is not None:
                    output = result
            except Exception as e:
                logger.warning("Post-hook for %s failed: %s", node_name, e)
        return output

    @classmethod
    def get_custom_agents(cls) -> Dict[str, CustomAgentFactory]:
        return dict(cls._custom_agents)

    @classmethod
    def list_plugins(cls) -> List[PluginManifest]:
        return list(cls._manifests.values())

    @classmethod
    def has_hooks(cls, node_name: str) -> bool:
        return bool(cls._pre_hooks.get(node_name) or cls._post_hooks.get(node_name))
