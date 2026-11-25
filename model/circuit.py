"""The Circuit: a set of components plus which terminals are connected.

Electrical *nodes* are groups of terminals that are joined by connections or
by ideal wires. We find them with union-find (a "disjoint set" structure):
every terminal starts in its own set, and each connection merges two sets.

Union-find cannot *un*-merge, so the circuit stores the raw list of
connections and rebuilds the node map on demand. That keeps removing a
component or a connection trivial, and rebuilding is nearly linear in the
number of terminals, which is negligible next to solving the matrix.
"""

from __future__ import annotations

from collections.abc import Hashable, Iterable
from typing import Generic, TypeVar

from model.components import Battery, Component, Terminal, Wire

T = TypeVar("T", bound=Hashable)
C = TypeVar("C", bound=Component)


class UnionFind(Generic[T]):
    """Disjoint sets with path halving and union by size (near O(1) per operation)."""

    def __init__(self, items: Iterable[T] = ()) -> None:
        self._parent: dict[T, T] = {}
        self._size: dict[T, int] = {}
        for item in items:
            self.find(item)

    def find(self, x: T) -> T:
        """Return the representative of x's set, adding x if it is new."""
        if x not in self._parent:
            self._parent[x] = x
            self._size[x] = 1
            return x
        while self._parent[x] != x:
            # Path halving: point x at its grandparent so later finds are shorter.
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: T, y: T) -> bool:
        """Merge the sets of x and y. Return False if they were already together."""
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return False
        if self._size[rx] < self._size[ry]:  # hang the smaller tree under the larger
            rx, ry = ry, rx
        self._parent[ry] = rx
        self._size[rx] += self._size[ry]
        return True


class Circuit:
    """Components and the connections between their terminals."""

    def __init__(self) -> None:
        self.components: list[Component] = []
        self.connections: list[tuple[Terminal, Terminal]] = []
        self.ground: Terminal | None = None  # None = choose automatically

    def add(self, component: C) -> C:
        """Add a component and return it (handy for ``r = c.add(Resistor(10))``)."""
        if component in self.components:
            raise ValueError(f"{component.label} is already in the circuit")
        self.components.append(component)
        return component

    def remove(self, component: Component) -> None:
        """Remove a component together with every connection touching it."""
        self.components.remove(component)
        self.connections = [
            (t1, t2)
            for t1, t2 in self.connections
            if t1.component is not component and t2.component is not component
        ]
        if self.ground is not None and self.ground.component is component:
            self.ground = None

    def connect(self, t1: Terminal, t2: Terminal) -> None:
        """Join two terminals so they become the same electrical node."""
        for t in (t1, t2):
            if t.component not in self.components:
                raise ValueError(f"{t} belongs to a component that is not in this circuit")
        self.connections.append((t1, t2))

    def node_map(self) -> dict[Terminal, int]:
        """Map every terminal to a node number 0..n-1 (terminals on one node share it)."""
        terminals = [t for comp in self.components for t in comp.terminals]
        uf: UnionFind[Terminal] = UnionFind(terminals)
        for t1, t2 in self.connections:
            uf.union(t1, t2)
        for comp in self.components:
            if isinstance(comp, Wire):
                uf.union(comp.a, comp.b)

        node_of_root: dict[Terminal, int] = {}
        result: dict[Terminal, int] = {}
        for t in terminals:
            root = uf.find(t)
            result[t] = node_of_root.setdefault(root, len(node_of_root))
        return result

    def ground_terminal(self) -> Terminal | None:
        """The terminal whose node is the 0 V reference.

        Uses ``self.ground`` if set; otherwise the minus terminal of the first
        battery (so readings look like "the battery's minus side is 0 V"), or
        the first terminal of the first component.
        """
        if self.ground is not None:
            return self.ground
        for comp in self.components:
            if isinstance(comp, Battery):
                return comp.minus
        return self.components[0].a if self.components else None
