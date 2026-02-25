"""Registry of board/circuit definitions used by the pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from src.circuit import Circuit

from .basic import build_led, build_rc_filter, build_voltage_divider
from .esp32s3 import build_esp32s3, esp32s3_placement


@dataclass(frozen=True)
class BoardSpec:
    name: str
    builder: Callable[[], Circuit]
    board_size: tuple[float, float]
    placement_factory: Callable[[], dict[str, tuple[float, float]]] | None = None

    def placement(self) -> dict[str, tuple[float, float]] | None:
        return self.placement_factory() if self.placement_factory else None


EXAMPLES: dict[str, BoardSpec] = {
    "led": BoardSpec(
        name="led",
        builder=build_led,
        board_size=(50.0, 50.0),
    ),
    "rc": BoardSpec(
        name="rc",
        builder=build_rc_filter,
        board_size=(50.0, 50.0),
    ),
    "divider": BoardSpec(
        name="divider",
        builder=build_voltage_divider,
        board_size=(50.0, 50.0),
    ),
    "esp32s3": BoardSpec(
        name="esp32s3",
        builder=build_esp32s3,
        board_size=(40.0, 80.0),
        placement_factory=esp32s3_placement,
    ),
}


def list_example_names() -> list[str]:
    return sorted(EXAMPLES.keys())


def get_example(name: str) -> BoardSpec:
    return EXAMPLES[name]
