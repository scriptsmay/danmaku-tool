"""danmaku-tool 前置环境检测脚本。

检测项目：
  1. uv 是否安装
  2. Python 版本 >= 3.12
  3. FFmpeg 是否可用
  4. FFmpeg NVENC 编码器是否可用
  5. NVIDIA GPU 状态（nvidia-smi）
  6. CJK 字体（微软雅黑 / Noto Sans CJK）

用法：
  python scripts/check_env.py
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass


def _enable_ansi() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


GREEN = "\033[32m"
RED = "\033[31m"
CYAN = "\033[36m"
BOLD = "\033[1m"
RESET = "\033[0m"

OK = f"{GREEN}✓{RESET}"
FAIL = f"{RED}✗{RESET}"


def run(cmd: list[str], timeout: int = 15) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, encoding="utf-8", errors="replace")
        return proc.returncode, proc.stdout.strip(), proc.stderr.strip()
    except FileNotFoundError:
        return -1, "", f"命令未找到: {cmd[0]}"
    except subprocess.TimeoutExpired:
        return -2, "", f"命令超时: {' '.join(cmd)}"


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    detail: str = ""


class EnvChecker:
    def __init__(self):
        self.results: list[CheckResult] = []

    def check_uv(self) -> None:
        rc, out, err = run(["uv", "--version"])
        if rc == 0 and "uv" in out:
            self.results.append(CheckResult("uv", True, out))
        else:
            self.results.append(CheckResult("uv", False, "未安装", err))

    def check_python(self) -> None:
        rc, out, _ = run([sys.executable, "--version"])
        if rc != 0:
            self.results.append(CheckResult("Python", False, "检测失败"))
            return
        ver_str = out.replace("Python ", "").strip()
        parts = tuple(int(p) for p in ver_str.split(".")[:2])
        if parts >= (3, 12):
            self.results.append(CheckResult("Python", True, f"{ver_str} (>= 3.12)"))
        else:
            self.results.append(CheckResult("Python", False, f"{ver_str} — 需要 >= 3.12"))

    def check_ffmpeg(self) -> None:
        rc, out, err = run(["ffmpeg", "-version"])
        if rc != 0:
            self.results.append(CheckResult("FFmpeg", False, "未安装或不在 PATH 中", err))
            return
        first_line = out.split("\n")[0] if out else ""
        self.results.append(CheckResult("FFmpeg", True, first_line[:80]))

    def check_nvenc(self) -> None:
        rc, out, _ = run(["ffmpeg", "-encoders"])
        if rc != 0:
            self.results.append(CheckResult("NVENC", False, "无法查询编码器列表"))
            return
        found = [e for e in ["h264_nvenc", "hevc_nvenc"] if e in out]
        if found:
            self.results.append(CheckResult("NVENC 编码器", True, f"可用 — {', '.join(found)}"))
        else:
            self.results.append(CheckResult("NVENC 编码器", False, "h264_nvenc 不可用", "检查 NVIDIA 驱动和 FFmpeg 编译选项"))

    def check_libx264(self) -> None:
        rc, out, _ = run(["ffmpeg", "-encoders"])
        if rc == 0 and "libx264" in out:
            self.results.append(CheckResult("libx264 (CPU)", True, "可用"))
        else:
            self.results.append(CheckResult("libx264 (CPU)", False, "不可用"))

    def check_subtitles_filter(self) -> None:
        rc, out, _ = run(["ffmpeg", "-filters"])
        if rc != 0:
            self.results.append(CheckResult("ASS 滤镜", False, "无法查询滤镜列表"))
            return
        has = "subtitles" in out or "ass" in out
        self.results.append(CheckResult("ASS 滤镜", has, "可用" if has else "不可用"))

    def check_nvidia_smi(self) -> None:
        rc, out, err = run(["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader"])
        if rc != 0:
            self.results.append(CheckResult("NVIDIA GPU", False, "nvidia-smi 不可用"))
            return
        info = out.strip().split("\n")[0] if out.strip() else ""
        self.results.append(CheckResult("NVIDIA GPU", True, info))

    def check_cjk_fonts(self) -> None:
        import os
        from pathlib import Path
        if sys.platform != "win32":
            self.results.append(CheckResult("CJK 字体", True, "非 Windows，跳过检测"))
            return
        fonts_dir = Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts"
        keywords = ["msyh", "simhei", "simsun", "noto", "source han", "wenquanyi", "dengxian"]
        found = []
        if fonts_dir.exists():
            for f in fonts_dir.iterdir():
                if f.suffix.lower() in (".ttf", ".ttc", ".otf"):
                    if any(kw in f.name.lower() for kw in keywords):
                        found.append(f.name)
        if found:
            display = found[:5]
            suffix = f" 等 {len(found)} 个" if len(found) > 5 else ""
            self.results.append(CheckResult("CJK 字体", True, f"{', '.join(display)}{suffix}"))
        else:
            self.results.append(CheckResult("CJK 字体", False, "未检测到 CJK 字体", "请安装微软雅黑或 Noto Sans CJK"))

    def run_all(self) -> None:
        print(f"\n{BOLD}{'─' * 50}{RESET}")
        print(f"{BOLD}  danmaku-tool 环境检测{RESET}")
        print(f"{BOLD}{'─' * 50}{RESET}\n")
        self.check_uv()
        self.check_python()
        self.check_ffmpeg()
        self.check_nvenc()
        self.check_libx264()
        self.check_subtitles_filter()
        self.check_nvidia_smi()
        self.check_cjk_fonts()

    def print_report(self) -> bool:
        print(f"\n{BOLD}{'─' * 50}{RESET}")
        print(f"{BOLD}  检测结果{RESET}")
        print(f"{BOLD}{'─' * 50}{RESET}\n")
        passed = failed = 0
        for r in self.results:
            icon = OK if r.passed else FAIL
            print(f"  {icon} {r.name:20s} {r.message}")
            if r.detail:
                print(f"    {CYAN}→ {r.detail}{RESET}")
            if r.passed:
                passed += 1
            else:
                failed += 1
        print(f"\n{BOLD}{'─' * 50}{RESET}")
        total = passed + failed
        if failed == 0:
            print(f"  {GREEN}{BOLD}全部通过！{RESET} ({passed}/{total})")
            print(f"\n  可以开始开发 danmaku-tool 了。")
            print(f"  下一步：uv run uvicorn danmaku_tool.main:app")
        else:
            print(f"  {RED}{BOLD}{failed} 项未通过{RESET}，{passed} 项通过")
            print(f"\n  请修复上述问题后重新运行此脚本。")
        print()
        return failed == 0


def main() -> None:
    _enable_ansi()
    checker = EnvChecker()
    checker.run_all()
    all_passed = checker.print_report()
    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
