"""Circuit components as plain dataclasses (no Qt, no NumPy).

Every component has exactly two terminals, ``terminals[0]`` and ``terminals[1]``
(also available as ``.a`` and ``.b``). Sign convention used everywhere:

* The *current* of a component is the current flowing **through it from
  terminal a to terminal b**.
* For a :class:`Battery`, ``a`` is the minus terminal and ``b`` the plus
  terminal, so its current is positive while it is discharging (current leaves
  through the plus terminal into the external circuit).

Components compare and hash by identity (``eq=False``): two 100 Ω resistors
are still two different parts, and that lets us use them as dict keys.
"""

from __future__ import annotations

import itertools
import math
from dataclasses import dataclass, field

_next_uid = itertools.count(1)


@dataclass(frozen=True)
class Terminal:
    """One connection point of a component (index 0 = a, 1 = b)."""

    component: Component
    index: int

    def __repr__(self) -> str:
        return f"{self.component.label}.{'ab'[self.index]}"


@dataclass(eq=False, kw_only=True)
class Component:
    """Base class for all two-terminal components."""

    name: str = ""
    uid: int = field(default_factory=lambda: next(_next_uid), init=False, repr=False)

    @property
    def terminals(self) -> tuple[Terminal, Terminal]:
        """Both terminals, (a, b)."""
        return Terminal(self, 0), Terminal(self, 1)

    @property
    def a(self) -> Terminal:
        """Terminal a (index 0)."""
        return Terminal(self, 0)

    @property
    def b(self) -> Terminal:
        """Terminal b (index 1)."""
        return Terminal(self, 1)

    @property
    def label(self) -> str:
        """Human-readable name used in error messages."""
        return self.name or f"{type(self).__name__} #{self.uid}"


def _require_finite(value: float, what: str) -> None:
    if not math.isfinite(value):
        raise ValueError(f"{what} must be a finite number, got {value!r}")


@dataclass(eq=False)
class Resistor(Component):
    """Ohmic resistor: V = I·R, with R > 0 in ohms."""

    resistance: float

    def __post_init__(self) -> None:
        _require_finite(self.resistance, "resistance")
        if self.resistance <= 0:
            raise ValueError(
                f"resistance must be > 0 Ω, got {self.resistance} "
                "(use a Wire for an ideal zero-resistance connection)"
            )


@dataclass(eq=False)
class Battery(Component):
    """DC voltage source with EMF ``voltage`` (V) and optional internal resistance (Ω).

    Terminal a is minus, terminal b is plus. With internal resistance r the
    terminal voltage is V_plus - V_minus = voltage - I·r.
    """

    voltage: float
    internal_resistance: float = 0.0

    def __post_init__(self) -> None:
        _require_finite(self.voltage, "voltage")
        _require_finite(self.internal_resistance, "internal_resistance")
        if self.internal_resistance < 0:
            raise ValueError(f"internal_resistance must be >= 0 Ω, got {self.internal_resistance}")

    @property
    def minus(self) -> Terminal:
        """Negative terminal (same as ``a``)."""
        return self.a

    @property
    def plus(self) -> Terminal:
        """Positive terminal (same as ``b``)."""
        return self.b

    @property
    def is_ideal(self) -> bool:
        """True when the battery has zero internal resistance."""
        return self.internal_resistance == 0


@dataclass(eq=False)
class Wire(Component):
    """Ideal zero-resistance connection.

    A wire never reaches the solver: :class:`model.circuit.Circuit` merges its two
    terminals into the same electrical node.
    """
