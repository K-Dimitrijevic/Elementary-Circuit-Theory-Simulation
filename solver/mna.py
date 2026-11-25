"""DC circuit solver using Modified Nodal Analysis (MNA).

The unknowns are the voltage of every node except ground (ground is 0 V by
definition), plus one current per *ideal* battery. We write one equation per
unknown and solve the linear system ``A·x = z``::

        [ G   B ] [ v ]   [ i ]
        [ Bᵀ  0 ] [ j ] = [ e ]

* ``G`` (n×n): conductances. Row k is Kirchhoff's current law (KCL) at node k:
  current leaving through conductances = current injected by sources.
* ``B`` (n×m): +1/-1 where ideal battery k touches a node, so the battery's
  current ``j_k`` takes part in KCL at its two nodes.
* The rows ``Bᵀ·v = e`` are the extra "modified" equations: V_plus - V_minus = E.

Ideal batteries need those extra rows because a voltage source has no finite
conductance to put into G. A battery *with* internal resistance r doesn't: by
Thevenin-Norton equivalence it is a current source E/r in parallel with a
conductance 1/r, which fits straight into G and i.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import numpy as np

from model.circuit import Circuit, UnionFind
from model.components import Battery, Component, Resistor, Terminal

#: Tiny conductance (siemens) from every node to ground. Like SPICE's GMIN, it
#: pins nodes that would otherwise float (a part not connected to ground) near
#: 0 V instead of leaving the matrix singular. Its error is about R·GMIN
#: relative, i.e. 1e-9 for a 1 kΩ circuit.
GMIN = 1e-12

#: Above roughly 1/machine-epsilon (~4.5e15) the solve cannot be trusted.
MAX_CONDITION = 1.0 / np.finfo(float).eps


class CircuitError(Exception):
    """The circuit has no unique DC solution (e.g. a short-circuited ideal battery)."""


@dataclass
class DCSolution:
    """Node voltages and component currents from :func:`solve_dc`."""

    node_of: dict[Terminal, int]
    node_voltages: np.ndarray  # indexed by node number; ground node is 0 V
    currents: dict[Component, float]  # through each component, from terminal a to b

    def voltage(self, terminal: Terminal) -> float:
        """Potential of a terminal relative to ground, in volts."""
        return float(self.node_voltages[self.node_of[terminal]])

    def voltage_between(self, plus: Terminal, minus: Terminal) -> float:
        """What a voltmeter reads with its red lead on ``plus`` and black on ``minus``."""
        return self.voltage(plus) - self.voltage(minus)

    def current(self, component: Component) -> float:
        """Current through a resistor or battery, from terminal a to b, in amperes."""
        return self.currents[component]


def solve_dc(circuit: Circuit, gmin: float = GMIN) -> DCSolution:
    """Solve a circuit of resistors, batteries and ideal wires at DC.

    Raises:
        CircuitError: if the circuit has no unique solution.
    """
    node_of = circuit.node_map()
    n_nodes = len(set(node_of.values()))
    ground_terminal = circuit.ground_terminal()
    if ground_terminal is None:  # empty circuit
        return DCSolution(node_of, np.zeros(0), {})
    ground = node_of[ground_terminal]

    resistors = [c for c in circuit.components if isinstance(c, Resistor)]
    batteries = [c for c in circuit.components if isinstance(c, Battery)]
    ideal = [b for b in batteries if b.is_ideal]
    norton = [b for b in batteries if not b.is_ideal]
    _check_ideal_batteries(ideal, node_of)

    # Matrix row of each non-ground node. Ground has no row: its voltage is known.
    row_of_node = {node: k for k, node in enumerate(n for n in range(n_nodes) if n != ground)}
    n, m = len(row_of_node), len(ideal)

    def row(t: Terminal) -> int | None:
        return row_of_node.get(node_of[t])  # None means "this terminal is on ground"

    A = np.zeros((n + m, n + m))
    z = np.zeros(n + m)

    for r in resistors:
        _stamp_conductance(A, row(r.a), row(r.b), 1.0 / r.resistance)

    for b in norton:
        g = 1.0 / b.internal_resistance
        _stamp_conductance(A, row(b.minus), row(b.plus), g)
        _stamp_current_source(z, row(b.minus), row(b.plus), b.voltage * g)

    for k, b in enumerate(ideal):
        col = n + k
        for t, sign in ((b.plus, 1.0), (b.minus, -1.0)):
            r_ = row(t)
            if r_ is not None:
                A[r_, col] += sign  # j_k enters KCL at this node
                A[col, r_] += sign  # and V_plus - V_minus appears in the constraint
        z[col] = b.voltage

    diag = np.arange(n)
    A[diag, diag] += gmin

    x = _solve(A, z)

    node_voltages = np.zeros(n_nodes)
    for node, k in row_of_node.items():
        node_voltages[node] = x[k]

    def v(t: Terminal) -> float:
        return float(node_voltages[node_of[t]])

    currents: dict[Component, float] = {}
    for r in resistors:
        currents[r] = (v(r.a) - v(r.b)) / r.resistance
    for b in norton:
        # Norton source pushes E/r from minus to plus; the parallel conductance
        # carries some of it back. The difference flows through the battery.
        currents[b] = (b.voltage - (v(b.plus) - v(b.minus))) / b.internal_resistance
    for k, b in enumerate(ideal):
        # j_k is defined as the current entering the plus terminal from outside,
        # i.e. flowing plus -> minus inside the battery. Our convention is minus -> plus.
        currents[b] = -float(x[n + k])

    return DCSolution(node_of, node_voltages, currents)


def _stamp_conductance(A: np.ndarray, p: int | None, q: int | None, g: float) -> None:
    """Add conductance g between rows p and q (None = ground)."""
    if p is not None:
        A[p, p] += g
    if q is not None:
        A[q, q] += g
    if p is not None and q is not None:
        A[p, q] -= g
        A[q, p] -= g


def _stamp_current_source(z: np.ndarray, src: int | None, dst: int | None, current: float) -> None:
    """Current source pushing ``current`` through itself from src to dst (into dst)."""
    if dst is not None:
        z[dst] += current
    if src is not None:
        z[src] -= current


def _check_ideal_batteries(ideal: list[Battery], node_of: dict[Terminal, int]) -> None:
    """Reject topologies where ideal batteries make A singular, with a clear message.

    Two cases (gmin cannot fix either, because both break KVL, not KCL):
    1. Both terminals on one node: a wire shorts the battery, demanding
       0 V = E and infinite current.
    2. A loop made only of ideal batteries: KVL around it either contradicts
       itself (different voltages) or leaves the current split undetermined.
    Ideal batteries are edges between nodes, so a loop exists exactly when an
    edge joins two nodes that are already connected: union-find again.
    """
    uf: UnionFind[int] = UnionFind()
    adjacency: dict[int, list[tuple[int, Battery]]] = {}
    for b in ideal:
        p, q = node_of[b.plus], node_of[b.minus]
        if p == q:
            raise CircuitError(
                f"{b.label} is short-circuited: a wire connects its terminals with no "
                "resistance in between, so the current would be infinite. Add a resistor "
                "or give the battery an internal resistance."
            )
        if not uf.union(p, q):
            loop = [other.label for other in _path(adjacency, p, q)] + [b.label]
            raise CircuitError(
                f"Ideal batteries {', '.join(loop)} form a loop with no resistance in it. "
                "Kirchhoff's voltage law around that loop either contradicts itself or "
                "leaves the current undetermined. Give one of them an internal resistance."
            )
        adjacency.setdefault(p, []).append((q, b))
        adjacency.setdefault(q, []).append((p, b))


def _path(adjacency: dict[int, list[tuple[int, Battery]]], start: int, goal: int) -> list[Battery]:
    """Batteries on the (unique) path between two nodes of the battery forest (BFS)."""
    came_from: dict[int, tuple[int, Battery] | None] = {start: None}
    queue = deque([start])
    while queue:
        node = queue.popleft()
        if node == goal:
            break
        for nxt, bat in adjacency.get(node, []):
            if nxt not in came_from:
                came_from[nxt] = (node, bat)
                queue.append(nxt)
    path: list[Battery] = []
    step = came_from.get(goal)
    while step is not None:
        prev, bat = step
        path.append(bat)
        step = came_from[prev]
    return path


def _solve(A: np.ndarray, z: np.ndarray) -> np.ndarray:
    """Solve A·x = z, turning numerical trouble into a CircuitError."""
    if A.size == 0:
        return np.zeros(0)
    try:
        x = np.linalg.solve(A, z)  # LU factorisation with partial pivoting
    except np.linalg.LinAlgError as exc:
        raise CircuitError("The circuit equations have no unique solution (singular matrix).") from exc
    # The topology check should catch every singular case; this is a backstop
    # for extreme values (e.g. 1e-20 Ω next to 1e20 Ω) that lose all precision.
    condition = np.linalg.cond(A)
    if not np.all(np.isfinite(x)) or condition > MAX_CONDITION:
        raise CircuitError(
            f"The circuit equations are numerically ill-conditioned (condition number "
            f"{condition:.1e}); check for extreme component values."
        )
    return x
