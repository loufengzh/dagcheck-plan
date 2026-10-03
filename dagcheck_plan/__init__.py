"""Validate and plan dependency graphs without running tasks."""
from .core import PlanError, plan, loads

__all__ = ["PlanError", "plan", "loads"]
__version__ = "0.1.0"
