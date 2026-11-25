# Elementary Circuit Theory Simulation

A desktop circuit construction kit in Python, in the spirit of PhET's Circuit
Construction Kit (AC). It runs as a standalone PySide6 window.

**Status: Milestone 1.** DC solver for resistors and batteries (Modified Nodal
Analysis) with tests, plus an empty main window. Building circuits in the GUI,
capacitors, inductors and AC come in later milestones.

## Setup

Requires Python 3.11 or newer.

```zsh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Run

```zsh
python main.py        # open the app
pytest                # run the solver tests
```

## Layout

| Folder    | Contents |
|-----------|----------|
| `model/`  | Components (dataclasses) and `Circuit`, which merges connected terminals into nodes with union-find |
| `solver/` | `mna.py`: Modified Nodal Analysis, builds and solves `A·x = z` with NumPy |
| `sim/`    | Time stepping (later) |
| `gui/`    | PySide6 window, canvas, toolbox |
| `tests/`  | pytest known-answer tests |

Dependencies point one way: `gui` imports `model`/`solver`/`sim`, never the
reverse, so the solver runs and is tested without opening a window.

## Using the solver from Python

```python
from model.circuit import Circuit
from model.components import Battery, Resistor
from solver.mna import solve_dc

c = Circuit()
bat = c.add(Battery(9.0, internal_resistance=1.0))
r = c.add(Resistor(8.0))
c.connect(bat.plus, r.a)
c.connect(r.b, bat.minus)

sol = solve_dc(c)
print(sol.current(r))                            # ≈ 1.0 A
print(sol.voltage_between(bat.plus, bat.minus))  # ≈ 8.0 V (tiny gmin error)
```

Sign convention: a component's current flows through it from terminal `a` to
terminal `b`. For a battery, `a` is minus and `b` is plus, so a discharging
battery has positive current.
