#!/usr/bin/env python3

import os
import sys

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")

import json
import platform
import re
import shutil
import subprocess
from pathlib import Path

SYSTEM = platform.system()
IS_WINDOWS = SYSTEM == "Windows"
BACKUP_SUFFIX = ".features-bak"

STATUS_ICON = {
    "off": "[ ]",
    "on": "[*]",
    "partial": "[~]",
    "unknown": "[?]",
}

STATUS_TEXT = {
    "off": "未开启",
    "on": "已开启",
    "partial": "部分",
    "unknown": "不兼容",
}

TOOLSEARCH_LOGIC_FIX_LABEL = "ToolSearch 逻辑修复"

WEBFETCH_BLOCKED_TARGET_RE = re.compile(
    rb'if\([A-Za-z_$][A-Za-z0-9_$]*\.data\.can_fetch===!0\)return[\s\S]{0,200}?\{status:"allowed"\};return\{status:"blocked"\}'
)
WEBFETCH_BLOCKED_PATCHED_RE = re.compile(
    rb'if\([A-Za-z_$][A-Za-z0-9_$]*\.data\.can_fetch===!0\)return[\s\S]{0,200}?\{status:"allowed"\};return\{status:"allowed"\}'
)
WEBFETCH_CHECK_FAILED_OLD = b'{status:"check_failed",error:'
WEBFETCH_CHECK_FAILED_NEW = b'{status:"allowed"/* */,error:'
NPM_TOOLSEARCH_LOGIC_FIX_OLD = (
    b"if(q.deferLoading)z.defer_loading=!0;"
    b"if(q.cacheControl)z.cache_control=q.cacheControl;"
)
NPM_TOOLSEARCH_LOGIC_FIX_NEW = (
    b"if(q.deferLoading)z.defer_loading=!0;"
    b"else if(q.cacheControl)z.cache_control=q.cacheControl;"
)
BUN_TOOLSEARCH_LOGIC_FIX_OLD = (
    b"if(A.deferLoading)D.defer_loading=!0;"
    b"if(A.cacheControl)D.cache_control=A.cacheControl;"
)
BUN_TOOLSEARCH_LOGIC_FIX_NEW = (
    b"A.deferLoading?D.defer_loading=!0:"
    b"A.cacheControl&&(D.cache_control=A.cacheControl)||0;"
)


def run_cmd(cmd: list[str], fallback: str = "") -> str:
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except Exception:
        return fallback
    return result.stdout.strip() if result.returncode == 0 else fallback


def run_cmd_lines(cmd: list[str]) -> list[str]:
    out = run_cmd(cmd)
    return [line.strip() for line in out.splitlines() if line.strip()]


class Installation:
    def __init__(
        self,
        target: Path,
        description: str,
        kind: str = "npm",
        command: Path | None = None,
        version: str = "",
    ):
        self.kind = kind
        self.target = self._resolve(target)
        self.command = self._resolve(command) if command else None
        self.description = description
        self.backup = self.target.parent / (self.target.name + BACKUP_SUFFIX)
        self.version = version or self._detect_version()

    @staticmethod
    def _resolve(path: Path) -> Path:
        try:
            return path.resolve(strict=True)
        except OSError:
            return path

    def _detect_version(self) -> str:
        if self.kind == "npm":
            version = _read_package_version(self.target.parent / "package.json")
            if version:
                return version
        if self.command:
            version = _read_command_version(self.command)
            if version:
                return version
        if self.kind == "bun":
            version = _read_command_version(self.target)
            if version:
                return version
        return "未知"

    def display_path(self) -> str:
        return str(self.target)

    def display_name(self) -> str:
        return self.target.name

    def command_display_path(self) -> str:
        if self.command:
            return str(self.command)
        return "未找到"

    def version_text(self) -> str:
        return self.version

    def backup_display_path(self) -> str:
        return str(self.backup.name)

    def __repr__(self) -> str:
        return (
            f"[{self.kind}] {self.description}\n"
            f"       版本: {self.version_text()}\n"
            f"       可执行文件: {self.command_display_path()}\n"
            f"       补丁目标文件: {self.display_path()}"
        )


def _read_package_version(package_json: Path) -> str:
    try:
        payload = json.loads(package_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return ""
    version = str(payload.get("version", "")).strip()
    return version


def _read_command_version(command: Path) -> str:
    out = run_cmd([str(command), "--version"])
    if not out:
        return ""
    return out.splitlines()[0].strip()


class PatchItem:
    def __init__(self, item_id: str, label: str, category: str):
        self.item_id = item_id
        self.label = label
        self.category = category

    def supports_close(self) -> bool:
        return True

    def note(self, data: bytes) -> str:
        return ""

    def status(self, data: bytes) -> str:
        raise NotImplementedError

    def apply(self, data: bytes) -> tuple[bytes, int]:
        raise NotImplementedError

    def revert(self, data: bytes) -> tuple[bytes, int]:
        raise NotImplementedError


class RegexPatch(PatchItem):
    def __init__(
        self,
        item_id: str,
        label: str,
        category: str,
        target_re: re.Pattern[bytes],
        patched_re: re.Pattern[bytes],
        replace_fn,
        revert_fn=None,
    ):
        super().__init__(item_id, label, category)
        self.target_re = target_re
        self.patched_re = patched_re
        self.replace_fn = replace_fn
        self.revert_fn = revert_fn

    def supports_close(self) -> bool:
        return self.revert_fn is not None

    def status(self, data: bytes) -> str:
        has_target = bool(self.target_re.search(data))
        has_patched = bool(self.patched_re.search(data))
        if has_target and not has_patched:
            return "off"
        if has_patched and not has_target:
            return "on"
        if has_target and has_patched:
            return "partial"
        return "unknown"

    def apply(self, data: bytes) -> tuple[bytes, int]:
        count = 0

        def _replace(match: re.Match[bytes]) -> bytes:
            nonlocal count
            count += 1
            return self.replace_fn(match)

        return self.target_re.sub(_replace, data), count

    def revert(self, data: bytes) -> tuple[bytes, int]:
        if self.revert_fn is None:
            return data, 0

        count = 0

        def _replace(match: re.Match[bytes]) -> bytes:
            nonlocal count
            count += 1
            return self.revert_fn(match)

        return self.patched_re.sub(_replace, data), count


def _build_gate_patch(gate_name: str, label: str, category: str) -> RegexPatch:
    target_re = re.compile(re.escape(gate_name.encode()) + b'",!1')
    patched_re = re.compile(re.escape(gate_name.encode()) + b'",!0')
    return RegexPatch(
        item_id=gate_name,
        label=label,
        category=category,
        target_re=target_re,
        patched_re=patched_re,
        replace_fn=lambda match: match.group(0).replace(b"!1", b"!0", 1),
        revert_fn=lambda match: match.group(0).replace(b"!0", b"!1", 1),
    )


def _build_bytes_patch(
    item_id: str,
    label: str,
    category: str,
    target: bytes,
    patched: bytes,
) -> RegexPatch:
    return RegexPatch(
        item_id=item_id,
        label=label,
        category=category,
        target_re=re.compile(re.escape(target)),
        patched_re=re.compile(re.escape(patched)),
        replace_fn=lambda match: patched,
        revert_fn=lambda match: target,
    )


def _replace_last(data: bytes, old: bytes, new: bytes) -> bytes:
    idx = data.rfind(old)
    if idx < 0:
        return data
    return data[:idx] + new + data[idx + len(old) :]


def _build_patch_set(logic_fix_old: bytes, logic_fix_new: bytes) -> list[PatchItem]:
    return [
        _build_gate_patch("tengu_kairos_cron", "/loop 定时循环任务", "功能门控"),
        RegexPatch(
            item_id="fetch_preflight_blocked",
            label="WebFetch 预检 blocked 绕过",
            category="网络限制",
            target_re=WEBFETCH_BLOCKED_TARGET_RE,
            patched_re=WEBFETCH_BLOCKED_PATCHED_RE,
            replace_fn=lambda match: match.group(0).replace(
                b'{status:"blocked"}',
                b'{status:"allowed"}',
                1,
            ),
            revert_fn=lambda match: _replace_last(
                match.group(0),
                b'{status:"allowed"}',
                b'{status:"blocked"}',
            ),
        ),
        _build_bytes_patch(
            item_id="fetch_preflight_checkfail",
            label="WebFetch 预检 check_failed 绕过",
            category="网络限制",
            target=WEBFETCH_CHECK_FAILED_OLD,
            patched=WEBFETCH_CHECK_FAILED_NEW,
        ),
        _build_bytes_patch(
            item_id="toolsearch_logic_fix",
            label=TOOLSEARCH_LOGIC_FIX_LABEL,
            category="逻辑修复",
            target=logic_fix_old,
            patched=logic_fix_new,
        ),
    ]


PATCHES_BY_KIND = {
    "npm": _build_patch_set(NPM_TOOLSEARCH_LOGIC_FIX_OLD, NPM_TOOLSEARCH_LOGIC_FIX_NEW),
    "bun": _build_patch_set(BUN_TOOLSEARCH_LOGIC_FIX_OLD, BUN_TOOLSEARCH_LOGIC_FIX_NEW),
}


def get_patches(inst: Installation) -> list[PatchItem]:
    return PATCHES_BY_KIND.get(inst.kind, PATCHES_BY_KIND["npm"])


def _dedupe_installations(items: list[Installation]) -> list[Installation]:
    unique: dict[str, Installation] = {}
    for item in items:
        unique[str(item.target).lower()] = item
    return list(unique.values())


def _find_npm() -> list[Installation]:
    results: list[Installation] = []

    npm_commands = _find_claude_commands()
    npm_root = run_cmd(["npm", "root", "-g"])
    if npm_root:
        cli = Path(npm_root) / "@anthropic-ai" / "claude-code" / "cli.js"
        if cli.is_file():
            command = next(
                (
                    path
                    for path in npm_commands
                    if path.suffix.lower() in (".cmd", ".ps1", ".bat")
                ),
                None,
            )
            results.append(Installation(cli, "npm 全局安装", "npm", command=command))

    if IS_WINDOWS:
        for command in npm_commands:
            cli = (
                command.resolve().parent
                / "node_modules"
                / "@anthropic-ai"
                / "claude-code"
                / "cli.js"
            )
            if cli.is_file():
                results.append(
                    Installation(cli, "npm 全局安装", "npm", command=command)
                )

    return _dedupe_installations(results)


def _find_claude_commands() -> list[Path]:
    if IS_WINDOWS:
        entries = run_cmd_lines(["where", "claude"])
    else:
        entries = run_cmd_lines(["which", "-a", "claude"])
    results: list[Path] = []
    for entry in entries:
        path = Installation._resolve(Path(entry))
        if path.is_file():
            results.append(path)
    return results


def _find_bun() -> list[Installation]:
    results: list[Installation] = []
    seen: set[str] = set()
    for path in _find_claude_commands():
        suffix = path.suffix.lower()
        if suffix in (".cmd", ".bat", ".ps1"):
            continue
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        results.append(Installation(path, "bun 原生安装", "bun", command=path))
    return _dedupe_installations(results)


def find_all() -> list[Installation]:
    return _dedupe_installations(_find_npm() + _find_bun())


def _write_via_rename(target: Path, data: bytes) -> bool:
    tmp = target.with_suffix(target.suffix + ".tmp")
    old = target.with_suffix(target.suffix + ".old")
    for path in (tmp, old):
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass

    tmp.write_bytes(data)
    try:
        target.rename(old)
    except OSError:
        tmp.unlink(missing_ok=True)
        print(f"  x 无法替换 {target.name}，请关闭 claude 后重试。")
        return False

    tmp.rename(target)
    try:
        old.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def write_safe(target: Path, data: bytes) -> bool:
    try:
        target.write_bytes(data)
        return True
    except PermissionError:
        print("  文件被占用，使用重命名方式替换...")
        return _write_via_rename(target, data)


def _display_width(text: str) -> int:
    import unicodedata

    width = 0
    for ch in text:
        width += 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
    return width


def _pad_right(text: str, width: int) -> str:
    return text + " " * max(0, width - _display_width(text))


def show_table(data: bytes, patches: list[PatchItem]):
    print()
    previous_category = ""
    for index, patch in enumerate(patches, 1):
        if patch.category != previous_category:
            print(f"  ── {patch.category} {'─' * (50 - len(patch.category) * 2)}")
            previous_category = patch.category

        status = patch.status(data)
        icon = STATUS_ICON.get(status, "[?]")
        text = STATUS_TEXT.get(status, "???") + patch.note(data)
        label_col = _pad_right(patch.label, 34)
        print(f"  {index:>2}. {icon} {label_col} {text}")
    print()


def _parse_indices(raw: str, patch_count: int) -> list[int] | None:
    indices: list[int] = []
    for part in raw.replace(",", " ").split():
        try:
            if "-" in part:
                start, end = part.split("-", 1)
                lo, hi = int(start), int(end)
                if lo > hi:
                    lo, hi = hi, lo
                for value in range(lo - 1, min(hi, patch_count)):
                    if 0 <= value < patch_count:
                        indices.append(value)
            else:
                value = int(part) - 1
                if 0 <= value < patch_count:
                    indices.append(value)
        except ValueError:
            return None
    return indices or None


def _apply_patches(
    inst: Installation,
    data: bytes,
    patches: list[PatchItem],
    action: str,
) -> bytes:
    new_data = data
    total = 0

    for patch in patches:
        if action == "open":
            new_data, count = patch.apply(new_data)
        else:
            new_data, count = patch.revert(new_data)

        if count == 0:
            continue

        prefix = "+" if action == "open" else "-"
        print(f"  {prefix} {patch.label} ({count} 处)")
        total += count

    if total == 0:
        print("  无需修改（已是目标状态或版本不兼容）。")
        return data

    if not inst.backup.is_file():
        shutil.copy2(inst.target, inst.backup)
        print(f"  已备份到 {inst.backup_display_path()}")

    if not write_safe(inst.target, new_data):
        return data

    print(f"  完成，共修改 {total} 处。重启 claude 生效。")
    return new_data


def interactive(inst: Installation):
    data = inst.target.read_bytes()
    patches = get_patches(inst)
    first = True

    while True:
        if not first:
            _wait()
        first = False
        _clear()

        print("=" * 60)
        print("  Claude Code 限制解除工具")
        print("=" * 60)
        print(f"  类型: [{inst.kind}] {inst.description}")
        print(f"  版本: {inst.version_text()}")
        print(f"  可执行文件: {inst.command_display_path()}")
        print(f"  补丁目标文件: {inst.display_path()}")
        show_table(data, patches)
        print("  命令:")
        print("    /open  编号   开启指定项      /open 2       /open 1-4     /open 2,3")
        print("    /close 编号   关闭指定项      /close 2      /close 2-4")
        print("    /all          开启全部四项")
        print("    /reset        关闭全部四项")
        print("    /restore      从备份恢复原始目标文件")
        print("    q             退出")
        print()

        try:
            command = input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n  已退出。")
            return

        lowered = command.lower()
        if lowered in ("q", "quit", "exit"):
            return

        if lowered == "/all":
            targets = [patch for patch in patches if patch.status(data) != "on"]
            if not targets:
                print("  全部已开启，无需操作。")
                continue
            data = _apply_patches(inst, data, targets, "open")
            continue

        if lowered == "/reset":
            targets = [
                patch
                for patch in patches
                if patch.supports_close() and patch.status(data) in ("on", "partial")
            ]
            if not targets:
                print("  无可关闭的项。")
                continue
            data = _apply_patches(inst, data, targets, "close")
            continue

        if lowered == "/restore":
            restore(inst)
            data = inst.target.read_bytes()
            continue

        if lowered.startswith("/open"):
            indices = _parse_indices(command[5:].strip(), len(patches))
            if indices is None:
                print("  无效编号。示例: /open 1-4")
                continue
            targets = [
                patches[index]
                for index in indices
                if patches[index].status(data) != "on"
            ]
            if not targets:
                print("  所选项已全部开启。")
                continue
            data = _apply_patches(inst, data, targets, "open")
            continue

        if lowered.startswith("/close"):
            indices = _parse_indices(command[6:].strip(), len(patches))
            if indices is None:
                print("  无效编号。示例: /close 2-4")
                continue
            targets = [
                patches[index]
                for index in indices
                if patches[index].supports_close()
                and patches[index].status(data) in ("on", "partial")
            ]
            if not targets:
                print("  所选项已全部关闭。")
                continue
            data = _apply_patches(inst, data, targets, "close")
            continue

        print("  未知命令。输入 /open /close /all /reset /restore 或 q")


def auto_enable_all(inst: Installation):
    data = inst.target.read_bytes()
    patches = get_patches(inst)
    targets = [patch for patch in patches if patch.status(data) != "on"]

    if not targets:
        print("  全部已开启，无需修改。")
        return

    _apply_patches(inst, data, targets, "open")


def restore(inst: Installation):
    if not inst.backup.is_file():
        print(f"  x 未找到备份 {inst.backup_display_path()}")
        return

    data = inst.backup.read_bytes()
    if not write_safe(inst.target, data):
        return

    print("  已从备份恢复。")


def select_installation(installations: list[Installation]) -> Installation | None:
    if len(installations) == 1:
        return installations[0]

    print(f"\n  检测到 {len(installations)} 个可用安装:\n")
    for index, inst in enumerate(installations, 1):
        print(f"    {index}. {inst}")
        print()

    while True:
        try:
            choice = input("  选择目标 (编号, q 退出): ").strip()
        except (EOFError, KeyboardInterrupt):
            return None
        if choice.lower() == "q":
            return None
        try:
            index = int(choice) - 1
            if 0 <= index < len(installations):
                return installations[index]
        except ValueError:
            pass
        print("  无效输入。")


def _print_help():
    name = Path(sys.argv[0]).name
    print(
        f"""
  Claude Code 限制解除工具

  用法: python {name} [选项]

    选项:
    (无参数)            交互式菜单
    --auto              一键解除四项限制
    --restore           从备份恢复原始目标文件
    --help              显示本帮助信息

  交互式命令:
    /open  编号         开启指定项      /open 2       /open 1-4     /open 2,3
    /close 编号         关闭指定项      /close 2      /close 2-4
    /all                开启全部四项
    /reset              关闭全部四项
    /restore            从备份恢复原始目标文件
    q                   退出

  说明:
    - 支持 npm 全局安装与 bun 原生安装
    - 菜单会显示当前目标的实际版本与本机路径
    - 自动检测 npm root -g，并从 PATH 中查找 claude 可执行文件
    - ToolSearch 逻辑修复会把 defer_loading 与 cache_control 改为互斥
    - 首次修改时自动创建 .features-bak 备份
    - 修改后需重启 claude 生效
"""
    )


def _parse_args() -> str:
    mode = "interactive"
    index = 1

    while index < len(sys.argv):
        arg = sys.argv[index]
        if arg in ("--help", "-h"):
            _print_help()
            raise SystemExit(0)
        if arg == "--auto":
            mode = "auto"
        elif arg == "--restore":
            mode = "restore"
        else:
            print(f"  x 未知参数: {arg}")
            raise SystemExit(1)
        index += 1

    return mode


def main():
    mode = _parse_args()

    installations = find_all()
    if not installations:
        print("\n  未检测到可用的 Claude Code 安装。")
        print("  请先确认已通过 npm 或 bun 完成安装。")
        _pause()
        raise SystemExit(1)

    inst = select_installation(installations)
    if inst is None:
        print("  已取消。")
        _pause()
        return

    if mode == "restore":
        restore(inst)
    elif mode == "auto":
        auto_enable_all(inst)
    else:
        interactive(inst)

    _pause()


def _clear():
    os.system("cls" if os.name == "nt" else "clear")


def _wait():
    try:
        if os.name == "nt":
            import msvcrt

            print("\n  按任意键继续...", end="", flush=True)
            msvcrt.getch()
            print()
        else:
            input("\n  按回车键继续...")
    except (EOFError, KeyboardInterrupt):
        pass


def _pause():
    try:
        input("\n  按回车键退出...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
