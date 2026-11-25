"""Known-answer tests for the DC MNA solver."""

from __future__ import annotations

import pytest

from model.circuit import Circuit
from model.components import Battery, Resistor, Wire
from solver.mna import CircuitError, solve_dc

# gmin (1e-12 S per node) leaks ~V·gmin to ground at every node, a relative error
# of order R·gmin·(number of nodes). 1e-8 sits above that, and far below any real bug.
REL = 1e-8


def approx(value: float) -> object:
    return pytest.approx(value, rel=REL, abs=1e-12)


def series_loop(circuit: Circuit, *parts) -> None:
    """Connect parts in a ring: parts[0].b -> parts[1].a -> ... -> parts[0].a."""
    for left, right in zip(parts, parts[1:] + parts[:1]):
        circuit.connect(left.b, right.a)


def test_voltage_divider() -> None:
    c = Circuit()
    bat = c.add(Battery(10.0))
    r1 = c.add(Resistor(1000.0))
    r2 = c.add(Resistor(2000.0))
    series_loop(c, bat, r1, r2)

    sol = solve_dc(c)

    # V_mid = E · R2 / (R1 + R2)
    assert sol.voltage(r1.b) == approx(10.0 * 2000 / 3000)
    assert sol.voltage(bat.minus) == 0.0  # automatic ground
    assert sol.voltage(bat.plus) == approx(10.0)


def test_series_resistors() -> None:
    c = Circuit()
    bat = c.add(Battery(6.0))
    rs = [c.add(Resistor(r)) for r in (100.0, 200.0, 300.0)]
    series_loop(c, bat, *rs)

    sol = solve_dc(c)

    expected = 6.0 / 600.0  # R_total = sum of resistances
    for r in rs:
        assert sol.current(r) == approx(expected)
        assert sol.voltage_between(r.a, r.b) == approx(expected * r.resistance)
    assert sol.current(bat) == approx(expected)


def test_parallel_resistors() -> None:
    c = Circuit()
    bat = c.add(Battery(12.0))
    r1 = c.add(Resistor(100.0))
    r2 = c.add(Resistor(300.0))
    # Both resistors directly across the battery, r2 attached via ideal wires.
    w_top, w_bottom = c.add(Wire()), c.add(Wire())
    c.connect(bat.plus, r1.a)
    c.connect(r1.b, bat.minus)
    c.connect(r1.a, w_top.a)
    c.connect(w_top.b, r2.a)
    c.connect(r1.b, w_bottom.a)
    c.connect(w_bottom.b, r2.b)

    sol = solve_dc(c)

    r_parallel = 1.0 / (1 / 100.0 + 1 / 300.0)  # 75 Ω
    assert sol.current(bat) == approx(12.0 / r_parallel)
    assert sol.current(r1) == approx(12.0 / 100.0)
    assert sol.current(r2) == approx(12.0 / 300.0)


def test_battery_with_internal_resistance() -> None:
    c = Circuit()
    bat = c.add(Battery(9.0, internal_resistance=1.0))
    load = c.add(Resistor(8.0))
    series_loop(c, bat, load)

    sol = solve_dc(c)

    current = 9.0 / (8.0 + 1.0)  # I = E / (R + r)
    assert sol.current(bat) == approx(current)
    assert sol.current(load) == approx(current)
    # Terminal voltage sags below the EMF by I·r.
    assert sol.voltage_between(bat.plus, bat.minus) == approx(9.0 - current * 1.0)


def test_short_circuit_through_internal_resistance_is_allowed() -> None:
    c = Circuit()
    bat = c.add(Battery(9.0, internal_resistance=0.5))
    c.connect(bat.plus, bat.minus)

    assert solve_dc(c).current(bat) == approx(18.0)  # I = E / r


def test_current_direction_follows_terminal_convention() -> None:
    c = Circuit()
    bat = c.add(Battery(5.0))
    r = c.add(Resistor(10.0))
    # Resistor wired "backwards": its b terminal touches the battery's plus.
    c.connect(bat.plus, r.b)
    c.connect(r.a, bat.minus)

    sol = solve_dc(c)

    assert sol.current(bat) == approx(0.5)  # discharging -> positive
    assert sol.current(r) == approx(-0.5)  # flows b -> a, against the a -> b convention


def test_floating_island_keeps_correct_differences() -> None:
    c = Circuit()
    main_bat = c.add(Battery(3.0))
    main_r = c.add(Resistor(30.0))
    series_loop(c, main_bat, main_r)
    # A second loop that touches nothing else: only gmin ties it to ground.
    c.ground = main_bat.minus
    island_bat = c.add(Battery(9.0))
    island_r = c.add(Resistor(1000.0))
    series_loop(c, island_bat, island_r)

    sol = solve_dc(c)

    assert sol.current(main_r) == approx(0.1)
    assert sol.current(island_r) == approx(9.0 / 1000.0)
    assert sol.voltage_between(island_bat.plus, island_bat.minus) == approx(9.0)


def test_dangling_resistor_carries_no_current() -> None:
    c = Circuit()
    bat = c.add(Battery(5.0))
    load = c.add(Resistor(100.0))
    dangling = c.add(Resistor(470.0))
    series_loop(c, bat, load)
    c.connect(bat.plus, dangling.a)  # dangling.b is connected to nothing

    sol = solve_dc(c)

    # Only the gmin leak (1e-12 S × 5 V = 5e-12 A) flows into the open end.
    assert sol.current(dangling) == pytest.approx(0.0, abs=1e-10)
    assert sol.voltage(dangling.b) == approx(5.0)


def test_shorted_ideal_battery_raises() -> None:
    c = Circuit()
    bat = c.add(Battery(9.0, name="B1"))
    wire = c.add(Wire())
    c.connect(bat.plus, wire.a)
    c.connect(wire.b, bat.minus)

    with pytest.raises(CircuitError, match="B1 is short-circuited"):
        solve_dc(c)


def test_parallel_ideal_batteries_raise() -> None:
    c = Circuit()
    b1 = c.add(Battery(5.0, name="B1"))
    b2 = c.add(Battery(9.0, name="B2"))
    load = c.add(Resistor(10.0))
    c.connect(b1.plus, b2.plus)
    c.connect(b1.minus, b2.minus)
    c.connect(b1.plus, load.a)
    c.connect(load.b, b1.minus)

    with pytest.raises(CircuitError, match="B1, B2 form a loop"):
        solve_dc(c)


def test_empty_circuit() -> None:
    sol = solve_dc(Circuit())
    assert sol.node_voltages.size == 0


@pytest.mark.parametrize(
    "factory",
    [lambda: Resistor(0.0), lambda: Resistor(-5.0), lambda: Battery(9.0, internal_resistance=-1.0),
     lambda: Battery(float("nan"))],
)
def test_invalid_component_values_are_rejected(factory) -> None:
    with pytest.raises(ValueError):
        factory()
