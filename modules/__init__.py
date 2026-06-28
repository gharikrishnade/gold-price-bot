"""
modules — content-module registry for the multi-show video platform.

Importing this package registers all available shows. The engine selects a module
by key via ``get_module``.

Tracker: PLAT-001, PLAT-002.
"""
from modules.base import ContentModule, ValidationResult, REGISTRY, register, get_module
from modules.gold import GoldModule

register(GoldModule())

__all__ = ["ContentModule", "ValidationResult", "REGISTRY", "register", "get_module"]
