"""Probe Windows UI Automation trees for faster pywinauto scripting.

Examples:
  python scripts/uia_probe.py --list
  python scripts/uia_probe.py --title-re ".*WeChat.*|.*微信.*" --depth 4
  python scripts/uia_probe.py --class-re "Qt.*" --screenshot probe.png
"""

from __future__ import annotations

import argparse
import ctypes
import json
import re
import sys
import time
from pathlib import Path
from typing import Any

from pywinauto import Desktop


PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def configure_stdout() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def process_path(pid: int) -> str:
    if not pid:
        return ""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        return ""
    try:
        size = ctypes.wintypes.DWORD(32768)
        buffer = ctypes.create_unicode_buffer(size.value)
        ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size))
        return buffer.value if ok else ""
    finally:
        kernel32.CloseHandle(handle)


def rect_tuple(wrapper: Any) -> tuple[int, int, int, int] | None:
    try:
        rect = wrapper.rectangle()
        return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        return None


def safe_text(wrapper: Any) -> str:
    try:
        return wrapper.window_text()
    except Exception:
        return ""


def wrapper_info(wrapper: Any) -> dict[str, Any]:
    info = wrapper.element_info
    pid = getattr(info, "process_id", None) or 0
    path = process_path(pid)
    return {
        "title": safe_text(wrapper),
        "control_type": getattr(info, "control_type", "") or "",
        "class_name": getattr(info, "class_name", "") or "",
        "automation_id": getattr(info, "automation_id", "") or "",
        "name": getattr(info, "name", "") or "",
        "handle": getattr(info, "handle", None),
        "pid": pid,
        "process": Path(path).name if path else "",
        "process_path": path,
        "rectangle": rect_tuple(wrapper),
        "visible": safe_bool(lambda: wrapper.is_visible()),
        "enabled": safe_bool(lambda: wrapper.is_enabled()),
    }


def safe_bool(fn: Any) -> bool | None:
    try:
        return bool(fn())
    except Exception:
        return None


def matches(wrapper: Any, args: argparse.Namespace) -> bool:
    data = wrapper_info(wrapper)
    if args.pid is not None and data["pid"] != args.pid:
        return False
    if args.title_re and not re.search(args.title_re, data["title"], re.I):
        return False
    if args.class_re and not re.search(args.class_re, data["class_name"], re.I):
        return False
    if args.process_re:
        haystack = f'{data["process"]}\n{data["process_path"]}'
        if not re.search(args.process_re, haystack, re.I):
            return False
    if not args.include_hidden and data["visible"] is False:
        return False
    return True


def list_windows(args: argparse.Namespace) -> list[dict[str, Any]]:
    desktop = Desktop(backend=args.backend)
    windows = []
    for wrapper in desktop.windows():
        try:
            if matches(wrapper, args):
                windows.append(wrapper_info(wrapper))
        except Exception as exc:
            windows.append({"error": repr(exc)})
    return windows


def format_window_line(index: int, item: dict[str, Any]) -> str:
    rect = item.get("rectangle") or ("?", "?", "?", "?")
    return (
        f"[{index}] pid={item.get('pid')} process={item.get('process')!r} "
        f"class={item.get('class_name')!r} title={item.get('title')!r} "
        f"rect={rect}"
    )


def children_of(wrapper: Any) -> list[Any]:
    try:
        return wrapper.children()
    except Exception:
        return []


def build_tree(wrapper: Any, depth: int, max_children: int, level: int = 0) -> dict[str, Any]:
    node = wrapper_info(wrapper)
    if level >= depth:
        return node

    kids = children_of(wrapper)
    visible_kids = []
    for child in kids[:max_children]:
        try:
            visible_kids.append(build_tree(child, depth, max_children, level + 1))
        except Exception as exc:
            visible_kids.append({"error": repr(exc)})
    if len(kids) > max_children:
        visible_kids.append({"truncated": len(kids) - max_children})
    node["children"] = visible_kids
    return node


def short_locator(item: dict[str, Any]) -> str:
    parts = []
    if item.get("title"):
        parts.append(f'title={item["title"]!r}')
    if item.get("automation_id"):
        parts.append(f'auto_id={item["automation_id"]!r}')
    if item.get("control_type"):
        parts.append(f'control_type={item["control_type"]!r}')
    if item.get("class_name"):
        parts.append(f'class_name={item["class_name"]!r}')
    return ", ".join(parts) or "<no stable properties>"


def flatten_tree(node: dict[str, Any]) -> list[dict[str, Any]]:
    out = [node]
    for child in node.get("children", []):
        if "children" in child or "control_type" in child:
            out.extend(flatten_tree(child))
    return out


def print_tree(node: dict[str, Any], level: int = 0) -> None:
    indent = "  " * level
    if "truncated" in node:
        print(f"{indent}... {node['truncated']} more children")
        return
    if "error" in node:
        print(f"{indent}! {node['error']}")
        return
    rect = node.get("rectangle") or ""
    locator = short_locator(node)
    print(f"{indent}- {locator} rect={rect} pid={node.get('pid')}")
    for child in node.get("children", []):
        print_tree(child, level + 1)


def choose_window(args: argparse.Namespace) -> Any:
    desktop = Desktop(backend=args.backend)
    matches_found = []
    for wrapper in desktop.windows():
        if matches(wrapper, args):
            matches_found.append(wrapper)
    if not matches_found:
        raise SystemExit("No matching window. Try --list or relax the filters.")
    if args.index >= len(matches_found):
        raise SystemExit(f"--index {args.index} is out of range; matched {len(matches_found)} window(s).")
    return matches_found[args.index]


def save_screenshot(wrapper: Any, path: str) -> None:
    image = wrapper.capture_as_image()
    image.save(path)


def main() -> int:
    configure_stdout()
    parser = argparse.ArgumentParser(description="Inspect Windows UIA/win32 controls for pywinauto.")
    parser.add_argument("--backend", choices=["uia", "win32"], default="uia")
    parser.add_argument("--list", action="store_true", help="List matching top-level windows.")
    parser.add_argument("--title-re", help="Regex matched against window title.")
    parser.add_argument("--class-re", help="Regex matched against window class.")
    parser.add_argument("--process-re", help="Regex matched against process exe name/path.")
    parser.add_argument("--pid", type=int, help="Match a specific process id.")
    parser.add_argument("--index", type=int, default=0, help="Use the nth matched window.")
    parser.add_argument("--include-hidden", action="store_true", help="Include hidden windows.")
    parser.add_argument("--depth", type=int, default=3, help="Control tree depth to dump.")
    parser.add_argument("--max-children", type=int, default=80, help="Per-node child limit.")
    parser.add_argument("--json", dest="json_path", help="Write the dumped tree/list as JSON.")
    parser.add_argument("--screenshot", help="Save a screenshot of the selected window.")
    parser.add_argument("--focus", action="store_true", help="Focus the selected window before dumping.")
    parser.add_argument("--wait", type=float, default=0.0, help="Seconds to wait after focusing.")
    args = parser.parse_args()

    if args.list:
        windows = list_windows(args)
        for index, item in enumerate(windows):
            print(format_window_line(index, item))
        if args.json_path:
            Path(args.json_path).write_text(json.dumps(windows, ensure_ascii=False, indent=2), encoding="utf-8")
        return 0

    wrapper = choose_window(args)
    if args.focus:
        wrapper.set_focus()
        if args.wait:
            time.sleep(args.wait)

    if args.screenshot:
        save_screenshot(wrapper, args.screenshot)
        print(f"Saved screenshot: {args.screenshot}")

    tree = build_tree(wrapper, args.depth, args.max_children)
    print_tree(tree)

    controls = flatten_tree(tree)
    candidates = [
        item
        for item in controls
        if item.get("automation_id") or item.get("title") or item.get("control_type") in {"Edit", "Button", "ListItem", "MenuItem"}
    ]
    print()
    print(f"Locator candidates: {len(candidates)}")
    for item in candidates[:50]:
        print(f"  child_window({short_locator(item)})")
    if len(candidates) > 50:
        print(f"  ... {len(candidates) - 50} more")

    if args.json_path:
        Path(args.json_path).write_text(json.dumps(tree, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote JSON: {args.json_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
