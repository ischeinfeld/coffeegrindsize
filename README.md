# coffeegrindsize

Analyze coffee particle size distributions from photographs on your own computer.
This fork modernizes Jonathan Gagné's Tkinter application and preserves Chris
Satterlee's installer-tooling history.

## macOS development setup

Use standard CPython 3.14 (not the experimental free-threaded build). Tk must be
installed alongside the interpreter; installing a Python package named `tk` is
not sufficient.

```sh
brew install uv python@3.14 python-tk@3.14
uv venv --python /opt/homebrew/opt/python@3.14/bin/python3.14
uv sync --locked
uv run coffeegrindsize
```

On an Intel Mac the Homebrew prefix is `/usr/local`. The environment deliberately
uses Homebrew Python, whose matching Tk package is installed above. Verify the
interpreter with `uv run python -m tkinter` if window startup fails.

See [upstream provenance and historical manuals](docs/UPSTREAM.md).
