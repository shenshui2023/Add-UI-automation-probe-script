# Add UI Automation Probe Script

A small Windows helper for quickly inspecting desktop application windows before writing `pywinauto` automation scripts.

The goal is to avoid slow screenshot-first workflows. Run this probe first, check whether the target app exposes useful UI Automation controls, and then decide whether to automate with stable control locators or fall back to relative coordinates/screenshots.

## Requirements

- Windows
- Python 3.9+
- `pywinauto`

Install the dependency:

```powershell
pip install pywinauto
```

If you have multiple Python installations, use the Python executable you normally use for automation:

```powershell
python -m pip install pywinauto
```

## Usage

List visible top-level windows:

```powershell
python scripts\uia_probe.py --list
```

Dump a window's UI Automation tree by title:

```powershell
python scripts\uia_probe.py --title-re "Codex" --depth 3
```

Find windows by class name:

```powershell
python scripts\uia_probe.py --class-re "Qt.*|Chrome_WidgetWin_1" --list
```

Find windows by process name or path:

```powershell
python scripts\uia_probe.py --process-re "WeChat|chrome" --list
```

Save the dumped tree as JSON:

```powershell
python scripts\uia_probe.py --title-re "Codex" --depth 4 --json probe.json
```

Focus a window before dumping it:

```powershell
python scripts\uia_probe.py --title-re "Codex" --focus --wait 0.5 --depth 3
```

Save a screenshot of the selected window:

```powershell
python scripts\uia_probe.py --title-re "Codex" --screenshot codex.png
```

## How To Use The Output

The script prints useful properties for each control:

- `title`
- `control_type`
- `class_name`
- `automation_id`
- `pid`
- `rectangle`

It also prints locator candidates such as:

```text
child_window(title='OK', control_type='Button')
```

You can turn those into `pywinauto` automation code:

```python
from pywinauto import Desktop

w = Desktop(backend="uia").window(title_re=".*Example.*")
w.child_window(title="OK", control_type="Button").click_input()
```

## Recommended Workflow

1. Run `--list` to find the target window.
2. Dump the target window with `--title-re`, `--class-re`, `--process-re`, or `--pid`.
3. Prefer stable locators such as `automation_id`, `title`, and `control_type`.
4. Use relative coordinates only when the app does not expose useful controls.
5. Use screenshots only for verification or failure diagnosis.

## Notes

Some apps use custom rendering, game engines, Electron, Qt, or protected surfaces. In those cases, UI Automation may only expose a few large panels instead of real buttons and input fields. That usually means coordinate-based automation is more practical.

For coordinate-based automation, keep the target window at a fixed size and calculate click positions relative to the window rectangle instead of absolute screen coordinates.
