#!/usr/bin/env python3
"""
解除 Claude Code 的 Tool Search 域名限制补丁脚本

支持:
  - 操作系统: macOS / Windows / Linux
  - 安装方式: bun 官方二进制 / npm 全局安装 / pnpm 全局安装 / VS Code·Cursor 扩展

原理:
  将 _a() 函数中 return["api.anthropic.com"].includes(...) 检查
  替换为 return!0（始终返回 true），等长字节替换，不改变文件大小。

用法:
  python patch-claude-toolsearch.py          # 交互式选择
  python patch-claude-toolsearch.py --auto   # 自动补丁所有找到的安装
  python patch-claude-toolsearch.py --restore # 从备份恢复
"""

import sys
import os
import re
import shutil
import platform
import subprocess
from pathlib import Path

# ── 补丁定义 ──────────────────────────────────────────────────────────

# 正则匹配任意合法 JS 标识符作为变量名，兼容所有混淆版本
PATCH_TARGET_RE = re.compile(
    rb'return\["api\.anthropic\.com"\]\.includes\(([A-Za-z_$][A-Za-z0-9_$]*)\)\}catch\{return!1\}'
)
PATCHED_RE = re.compile(rb"return!0/\* *\*/\}catch\{return!0\}")

_PATCH_PREFIX = b"return!0/*"
_PATCH_SUFFIX = b"*/}catch{return!0}"


def build_patched_bytes(length: int) -> bytes:
    """根据匹配长度动态生成等长替换字节"""
    padding = length - len(_PATCH_PREFIX) - len(_PATCH_SUFFIX)
    if padding < 0:
        raise ValueError(f"补丁模板过长: {length}")
    return _PATCH_PREFIX + (b" " * padding) + _PATCH_SUFFIX


def get_patch_status(data: bytes) -> str:
    if PATCH_TARGET_RE.search(data):
        return "unpatched"
    if PATCHED_RE.search(data):
        return "patched"
    return "unknown"


def patch_bytes(data: bytes) -> tuple[bytes, int]:
    count = 0

    def replace(match: re.Match[bytes]) -> bytes:
        nonlocal count
        count += 1
        return build_patched_bytes(len(match.group(0)))

    return PATCH_TARGET_RE.sub(replace, data), count


def resolve_patch_target(path: Path) -> Path:
    """解析符号链接到实际文件"""
    try:
        return path.resolve(strict=True)
    except OSError:
        return path


def resign_if_needed(path: Path) -> tuple[bool, str]:
    """macOS 上修改二进制后需要 ad-hoc 重签名"""
    if SYSTEM != "Darwin":
        return True, ""
    result = subprocess.run(
        ["codesign", "--force", "--sign", "-", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0:
        return True, "已完成 macOS ad-hoc 重签名。"
    message = (result.stderr or result.stdout).strip() or "codesign 执行失败"
    return False, message


BACKUP_SUFFIX = ".toolsearch-bak"

# ── 平台检测 ──────────────────────────────────────────────────────────

SYSTEM = platform.system()  # Darwin / Windows / Linux
IS_WINDOWS = (
    SYSTEM == "Windows"
    or "MSYS" in os.environ.get("MSYSTEM", "")
    or "MINGW" in platform.platform()
)


def home() -> Path:
    return Path.home()


def run_cmd(cmd: list[str], fallback: str = "") -> str:
    if not shutil.which(cmd[0]):
        return fallback
    try:
        r = subprocess.run(
            cmd, capture_output=True, text=True, timeout=5, shell=IS_WINDOWS
        )
        return r.stdout.strip() if r.returncode == 0 else fallback
    except Exception:
        return fallback


# ── 安装探测 ──────────────────────────────────────────────────────────


def _find_patch_target_in_pkg(pkg_dir: Path) -> Path | None:
    """在 npm/pnpm 包目录中搜索包含域名检查代码的文件，返回实际补丁目标"""
    # 优先检查 cli.js（最常见）
    cli_js = pkg_dir / "cli.js"
    if cli_js.is_file() and b"api.anthropic.com" in cli_js.read_bytes():
        return cli_js
    # 搜索包目录下其他 JS 文件
    for js_file in sorted(pkg_dir.rglob("*.js")):
        if js_file.stat().st_size < 1000:
            continue
        try:
            if b"api.anthropic.com" in js_file.read_bytes():
                return js_file
        except OSError:
            continue
    return None


class Installation:
    def __init__(self, kind: str, target: Path, description: str):
        self.kind = kind  # "bun" / "npm" / "pnpm"
        self.source = target  # 用户看到的入口路径
        self.target = resolve_patch_target(target)
        self.description = description
        self.backup = self.target.parent / (self.target.name + BACKUP_SUFFIX)

    def __repr__(self):
        return f"[{self.kind}] {self.description}\n       文件: {self.target}"


def find_bun_installations() -> list[Installation]:
    """查找 bun 官方安装的 claude 二进制"""
    results = []
    candidates: list[Path] = []

    if IS_WINDOWS:
        candidates.append(home() / ".local" / "bin" / "claude.exe")
    else:
        # macOS / Linux
        candidates.append(home() / ".claude" / "local" / "claude")
        candidates.append(home() / ".local" / "bin" / "claude")

    for p in candidates:
        if p.is_file():
            results.append(Installation("bun", p, f"Bun 官方安装 ({p})"))
    return results


def find_npm_installations() -> list[Installation]:
    """查找 npm 全局安装"""
    results = []

    npm_root = run_cmd(["npm", "root", "-g"])
    if npm_root:
        pkg_dir = Path(npm_root) / "@anthropic-ai" / "claude-code"
        if pkg_dir.is_dir():
            target = _find_patch_target_in_pkg(pkg_dir)
            if target:
                results.append(Installation("npm", target, f"npm 全局安装 ({target})"))
    else:
        # npm 命令不可用，尝试扫描版本管理器目录
        results.extend(_find_npm_fallback())
    return results


def _find_npm_fallback() -> list[Installation]:
    """npm 命令不可用时，搜索 nvm / fnm / volta 等版本管理器的安装路径"""
    h = home()
    search_dirs: list[tuple[Path, str]] = []  # (node_modules_dir, description)

    if IS_WINDOWS:
        appdata = Path(os.environ.get("APPDATA", ""))

        # 默认 npm 全局 (无版本管理器)
        if appdata.name:
            search_dirs.append((appdata / "npm" / "node_modules", "npm 默认全局"))

        # nvm-windows
        nvm_home = os.environ.get(
            "NVM_HOME", str(appdata / "nvm") if appdata.name else ""
        )
        if nvm_home:
            nvm_path = Path(nvm_home)
            if nvm_path.is_dir():
                for d in nvm_path.iterdir():
                    nm = d / "node_modules"
                    if d.is_dir() and nm.is_dir():
                        search_dirs.append((nm, f"nvm ({d.name})"))

        # fnm
        fnm_dir = Path(os.environ.get("FNM_DIR", str(h / ".fnm")))
        nv = fnm_dir / "node-versions"
        if nv.is_dir():
            for d in nv.iterdir():
                nm = d / "installation" / "node_modules"
                if nm.is_dir():
                    search_dirs.append((nm, f"fnm ({d.name})"))
    else:
        # nvm
        nvm_dir = Path(os.environ.get("NVM_DIR", str(h / ".nvm")))
        versions = nvm_dir / "versions" / "node"
        if versions.is_dir():
            for d in versions.iterdir():
                nm = d / "lib" / "node_modules"
                if nm.is_dir():
                    search_dirs.append((nm, f"nvm ({d.name})"))

        # fnm
        fnm_dir = Path(os.environ.get("FNM_DIR", str(h / ".fnm")))
        nv = fnm_dir / "node-versions"
        if nv.is_dir():
            for d in nv.iterdir():
                nm = d / "installation" / "lib" / "node_modules"
                if nm.is_dir():
                    search_dirs.append((nm, f"fnm ({d.name})"))

        # 系统级
        for p in [Path("/usr/local/lib/node_modules"), Path("/usr/lib/node_modules")]:
            if p.is_dir():
                search_dirs.append((p, "系统 npm"))

    # volta (跨平台)
    volta_home = Path(os.environ.get("VOLTA_HOME", str(h / ".volta")))
    volta_node = volta_home / "tools" / "image" / "node"
    if volta_node.is_dir():
        for d in volta_node.iterdir():
            nm = (d / "node_modules") if IS_WINDOWS else (d / "lib" / "node_modules")
            if nm.is_dir():
                search_dirs.append((nm, f"volta ({d.name})"))

    results: list[Installation] = []
    seen: set[str] = set()
    for nm_dir, desc in search_dirs:
        pkg_dir = nm_dir / "@anthropic-ai" / "claude-code"
        if pkg_dir.is_dir():
            target = _find_patch_target_in_pkg(pkg_dir)
            if target:
                key = str(target.resolve())
                if key not in seen:
                    seen.add(key)
                    results.append(
                        Installation("npm", target, f"npm ({desc}) ({target})")
                    )
    return results


def find_pnpm_installations() -> list[Installation]:
    """查找 pnpm 全局安装"""
    results = []

    pnpm_root = run_cmd(["pnpm", "root", "-g"])
    if not pnpm_root:
        return results

    pkg_dir = Path(pnpm_root) / "@anthropic-ai" / "claude-code"
    if pkg_dir.is_dir():
        target = _find_patch_target_in_pkg(pkg_dir)
        if target:
            results.append(
                Installation(
                    "pnpm", target.resolve(), f"pnpm 全局安装 ({target.resolve()})"
                )
            )
            return results

    # 回退：在 .pnpm 目录下搜索
    pnpm_dir = Path(pnpm_root).parent / ".pnpm"
    if pnpm_dir.is_dir():
        for pkg in pnpm_dir.rglob("@anthropic-ai/claude-code"):
            if pkg.is_dir():
                target = _find_patch_target_in_pkg(pkg)
                if target:
                    results.append(
                        Installation("pnpm", target, f"pnpm 全局安装 ({target})")
                    )
                    break
    return results


def find_brew_installations() -> list[Installation]:
    """查找 Homebrew cask 安装的 claude 二进制"""
    if IS_WINDOWS:
        return []
    results = []
    seen: set[str] = set()
    brew_prefix = run_cmd(["brew", "--prefix"])
    prefixes: list[Path] = []
    if brew_prefix:
        prefixes.append(Path(brew_prefix))
    for fallback in [Path("/opt/homebrew"), Path("/usr/local")]:
        if fallback not in prefixes and fallback.is_dir():
            prefixes.append(fallback)
    for prefix in prefixes:
        caskroom = prefix / "Caskroom" / "claude-code"
        if not caskroom.is_dir():
            continue
        for version_dir in sorted(caskroom.iterdir(), reverse=True):
            if not version_dir.is_dir() or version_dir.name.startswith("."):
                continue
            binary = version_dir / "claude"
            if binary.is_file() and binary.stat().st_size > 10 * 1024 * 1024:
                key = str(binary.resolve())
                if key not in seen:
                    seen.add(key)
                    results.append(
                        Installation(
                            "brew", binary, f"Homebrew cask ({version_dir.name})"
                        )
                    )
    return results


def find_vscode_installations() -> list[Installation]:
    """查找 VS Code / Cursor 扩展中的 Claude Code 捆绑二进制"""
    results = []
    search_bases = [
        ("vscode", "VS Code", home() / ".vscode" / "extensions"),
        ("vscode", "VS Code Insiders", home() / ".vscode-insiders" / "extensions"),
        ("cursor", "Cursor", home() / ".cursor" / "extensions"),
    ]
    for kind, label, base in search_bases:
        if not base.is_dir():
            continue
        ext_dirs = sorted(base.glob("anthropic.claude-code-*"), reverse=True)
        if not ext_dirs:
            continue
        ext_dir = ext_dirs[0]
        # 捆绑二进制 (>10MB)
        for name in ["claude.exe", "claude"] if IS_WINDOWS else ["claude"]:
            for p in ext_dir.rglob(name):
                if (
                    p.is_file()
                    and not p.name.endswith(".bak")
                    and p.stat().st_size > 10 * 1024 * 1024
                ):
                    results.append(
                        Installation(kind, p, f"{label} 捆绑二进制 ({ext_dir.name})")
                    )
    return results


def find_wsl_installations() -> list[Installation]:
    """在 WSL 发行版中查找 Claude Code 安装（仅 Windows）"""
    if not IS_WINDOWS:
        return []
    distro_names = _get_wsl_distros()
    if not distro_names:
        return []

    def _safe_is_dir(p: Path) -> bool:
        """WSL UNC 路径不可访问或权限不足时返回 False 而非抛异常"""
        try:
            return p.is_dir()
        except OSError:
            return False

    results: list[Installation] = []
    for dname in distro_names:
        distro = Path(f"//wsl.localhost/{dname}")
        if not _safe_is_dir(distro):
            continue
        # 收集用户主目录
        user_dirs: list[Path] = []
        home_base = distro / "home"
        if _safe_is_dir(home_base):
            try:
                user_dirs.extend(d for d in home_base.iterdir() if d.is_dir())
            except OSError:
                pass
        root_home = distro / "root"
        if _safe_is_dir(root_home):
            user_dirs.append(root_home)

        for udir in user_dirs:
            # bun 安装：实际二进制在 ~/.local/share/claude/versions/<ver>
            # ~/.local/bin/claude 是符号链接，从 Windows UNC 路径无法跟踪
            versions_dir = udir / ".local" / "share" / "claude" / "versions"
            if _safe_is_dir(versions_dir):
                try:
                    for v in sorted(versions_dir.iterdir(), reverse=True):
                        if v.name.endswith(BACKUP_SUFFIX):
                            continue
                        if v.is_file() and v.stat().st_size > 10 * 1024 * 1024:
                            results.append(
                                Installation("wsl", v, f"WSL ({dname}) bun v{v.name}")
                            )
                except OSError:
                    pass

            # npm: nvm / fnm / volta
            nm_search: list[tuple[Path, str]] = []
            nvm_node = udir / ".nvm" / "versions" / "node"
            if _safe_is_dir(nvm_node):
                try:
                    for v in nvm_node.iterdir():
                        nm = v / "lib" / "node_modules"
                        if v.is_dir() and nm.is_dir():
                            nm_search.append((nm, f"nvm {v.name}"))
                except OSError:
                    pass
            fnm_nv = udir / ".fnm" / "node-versions"
            if _safe_is_dir(fnm_nv):
                try:
                    for v in fnm_nv.iterdir():
                        nm = v / "installation" / "lib" / "node_modules"
                        if v.is_dir() and nm.is_dir():
                            nm_search.append((nm, f"fnm {v.name}"))
                except OSError:
                    pass
            volta_node = udir / ".volta" / "tools" / "image" / "node"
            if _safe_is_dir(volta_node):
                try:
                    for v in volta_node.iterdir():
                        nm = v / "lib" / "node_modules"
                        if v.is_dir() and nm.is_dir():
                            nm_search.append((nm, f"volta {v.name}"))
                except OSError:
                    pass

            for nm_dir, label in nm_search:
                pkg = nm_dir / "@anthropic-ai" / "claude-code"
                if _safe_is_dir(pkg):
                    target = _find_patch_target_in_pkg(pkg)
                    if target:
                        results.append(
                            Installation("wsl", target, f"WSL ({dname}) {label}")
                        )

        # 系统级 npm
        for sys_nm in [
            distro / "usr" / "local" / "lib" / "node_modules",
            distro / "usr" / "lib" / "node_modules",
        ]:
            pkg = sys_nm / "@anthropic-ai" / "claude-code"
            if _safe_is_dir(pkg):
                target = _find_patch_target_in_pkg(pkg)
                if target:
                    results.append(
                        Installation("wsl", target, f"WSL ({dname}) npm 系统")
                    )

    return results


def _get_wsl_distros() -> list[str]:
    """获取已安装的 WSL 发行版名称列表"""
    try:
        r = subprocess.run(
            ["wsl.exe", "--list", "--quiet"],
            capture_output=True,
            timeout=5,
        )
        if r.returncode != 0:
            return []
        text = r.stdout.decode("utf-16-le", errors="ignore").strip()
        return [l.strip() for l in text.splitlines() if l.strip()]
    except Exception:
        return []


def find_all_installations() -> list[Installation]:
    """探测系统中所有 Claude Code 安装"""
    all_inst: list[Installation] = []
    all_inst.extend(find_brew_installations())
    all_inst.extend(find_bun_installations())
    all_inst.extend(find_npm_installations())
    all_inst.extend(find_pnpm_installations())
    all_inst.extend(find_vscode_installations())
    all_inst.extend(find_wsl_installations())
    # 去重：brew 和 bun 的 symlink 可能指向同一文件
    seen: set[str] = set()
    deduped: list[Installation] = []
    for inst in all_inst:
        key = str(inst.target)
        if key not in seen:
            seen.add(key)
            deduped.append(inst)
    return deduped


# ── 补丁逻辑 ──────────────────────────────────────────────────────────


def check_status(inst: Installation) -> str:
    """检查安装的补丁状态: 'unpatched' / 'patched' / 'unknown'"""
    return get_patch_status(inst.target.read_bytes())


def _write_via_rename(target: Path, data: bytes) -> bool:
    """通过重命名方式写入被占用的文件（Windows 运行中的 exe 可重命名但不可覆写）"""
    tmp_path = target.with_suffix(target.suffix + ".tmp")
    old_path = target.with_suffix(target.suffix + ".old")

    # 清理之前可能残留的临时文件
    for p in (tmp_path, old_path):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass

    tmp_path.write_bytes(data)
    try:
        target.rename(old_path)
    except OSError:
        tmp_path.unlink(missing_ok=True)
        print(f"  ✗ 无法重命名 {target.name}，请关闭 claude 后重试。")
        return False

    tmp_path.rename(target)

    # 尝试删除旧文件（正在运行时可能删不掉，不影响功能）
    try:
        old_path.unlink(missing_ok=True)
    except OSError:
        pass
    return True


def apply_patch(inst: Installation) -> bool:
    """对目标文件应用补丁，返回是否成功"""
    data = inst.target.read_bytes()
    patched, count = patch_bytes(data)

    if count == 0:
        if get_patch_status(data) == "patched":
            print(f"  ✓ 已经补丁过了，跳过。")
            return True
        print(f"  ✗ 未找到目标字符串，可能版本不兼容。")
        return False

    # 备份
    shutil.copy2(inst.target, inst.backup)
    print(f"  已备份到 {inst.backup}")

    try:
        inst.target.write_bytes(patched)
    except PermissionError:
        print(f"  文件被占用，使用重命名方式替换...")
        if not _write_via_rename(inst.target, patched):
            return False

    ok, message = resign_if_needed(inst.target)
    if not ok:
        print(f"  ✗ 补丁已写入，但重签名失败: {message}")
        return False
    if message:
        print(f"  {message}")

    print(f"  ✓ 补丁成功，共替换 {count} 处。")
    return True


def restore_backup(inst: Installation) -> bool:
    """从备份恢复原始文件"""
    if not inst.backup.is_file():
        print(f"  ✗ 未找到备份文件 {inst.backup}")
        return False

    backup_data = inst.backup.read_bytes()

    try:
        inst.target.write_bytes(backup_data)
    except PermissionError:
        print(f"  文件被占用，使用重命名方式替换...")
        if not _write_via_rename(inst.target, backup_data):
            return False

    print(f"  ✓ 已从备份恢复。")
    return True


# ── 交互式菜单 ────────────────────────────────────────────────────────

STATUS_LABEL = {
    "unpatched": "未补丁",
    "patched": "已补丁",
    "unknown": "版本不兼容",
}


def interactive_menu(installations: list[Installation], mode: str = "patch"):
    """交互式选择目标"""
    action = "补丁" if mode == "patch" else "恢复"
    print(f"\n检测到 {len(installations)} 个 Claude Code 安装：\n")

    statuses = []
    for i, inst in enumerate(installations, 1):
        status = check_status(inst)
        statuses.append(status)
        has_backup = "有备份" if inst.backup.is_file() else "无备份"
        print(f"  {i}. [{inst.kind:4s}] {STATUS_LABEL[status]} | {has_backup}")
        print(f"         {inst.target}\n")

    if len(installations) > 1:
        print(f"  0. 全部{action}")
    print()

    while True:
        try:
            choice = input(f"请选择要{action}的目标 (输入编号，q 退出): ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return

        if choice.lower() == "q":
            print("已取消。")
            return

        try:
            num = int(choice)
        except ValueError:
            print("请输入有效编号。")
            continue

        if num == 0 and len(installations) > 1:
            targets = list(range(len(installations)))
            break
        elif 1 <= num <= len(installations):
            targets = [num - 1]
            break
        else:
            print("编号超出范围。")
            continue

    for idx in targets:
        inst = installations[idx]
        print(f"\n→ 处理: {inst}")
        if mode == "patch":
            apply_patch(inst)
        else:
            restore_backup(inst)

    print(f"\n完成。重启 claude 生效。")


def auto_mode(installations: list[Installation], mode: str = "patch"):
    """自动处理所有安装"""
    for inst in installations:
        print(f"\n→ 处理: {inst}")
        if mode == "patch":
            apply_patch(inst)
        else:
            restore_backup(inst)
    print(f"\n完成。重启 claude 生效。")


# ── 入口 ──────────────────────────────────────────────────────────────


def main():
    print("=" * 60)
    print("  Claude Code Tool Search 域名限制解除补丁")
    print("=" * 60)
    print(f"  系统: {SYSTEM} | Python {platform.python_version()}")
    print()

    mode = "patch"
    auto = False
    for arg in sys.argv[1:]:
        if arg == "--restore":
            mode = "restore"
        elif arg == "--auto":
            auto = True

    print("正在扫描 Claude Code 安装...")
    installations = find_all_installations()

    if not installations:
        print("\n未检测到任何 Claude Code 安装。")
        print(
            "支持的安装方式: bun 官方安装 / npm -g / pnpm add -g / VS Code·Cursor 扩展"
        )
        sys.exit(1)

    if auto:
        auto_mode(installations, mode)
    elif len(installations) == 1:
        inst = installations[0]
        print(f"\n检测到 1 个安装:")
        print(f"  {inst}")
        status = check_status(inst)
        print(f"  状态: {STATUS_LABEL[status]}")

        if mode == "patch" and status == "patched":
            print("\n已经补丁过了，无需操作。")
            _pause_if_needed(auto)
            return
        if mode == "restore" and not inst.backup.is_file():
            print("\n未找到备份，无法恢复。")
            _pause_if_needed(auto)
            return

        action = "应用补丁" if mode == "patch" else "恢复备份"
        try:
            confirm = input(f"\n是否{action}？(y/N): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n已取消。")
            return

        if confirm == "y":
            print()
            if mode == "patch":
                apply_patch(inst)
            else:
                restore_backup(inst)
            print(f"\n完成。重启 claude 生效。")
        else:
            print("已取消。")
    else:
        interactive_menu(installations, mode)

    _pause_if_needed(auto)


def _pause_if_needed(auto: bool):
    """非自动模式下暂停，防止双击运行时窗口闪退"""
    if auto:
        return
    try:
        input("\n按回车键退出...")
    except (EOFError, KeyboardInterrupt):
        pass


if __name__ == "__main__":
    main()
