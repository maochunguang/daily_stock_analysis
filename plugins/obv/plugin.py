"""Example external plugin entry. It reuses the built-in implementation."""

from personal.plugins.builtin.obv import OBVIndicator

__all__ = ["OBVIndicator"]
