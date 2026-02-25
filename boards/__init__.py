"""Board definitions and registry API."""

from .registry import BoardSpec, EXAMPLES, get_example, list_example_names

__all__ = [
    "BoardSpec",
    "EXAMPLES",
    "get_example",
    "list_example_names",
]
