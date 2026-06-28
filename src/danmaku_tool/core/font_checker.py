"""CJK 字体可用性检测（Windows）。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CJK_KEYWORDS = ["msyh", "yahei", "simhei", "simsun", "noto", "source han", "wenquanyi", "dengxian", "pingfang"]


def _strip_font_type_suffix(name: str) -> str:
    """去掉注册表字体名末尾的 (TrueType) / (OpenType) 等后缀。"""
    import re
    return re.sub(r"\s*\((?:TrueType|OpenType)\)\s*$", "", name).strip()


async def list_system_fonts() -> list[str]:
    """扫描 Windows 注册表，返回已安装的 CJK 字体显示名称列表。

    同时检查 HKLM（系统全局安装）和 HKCU（当前用户安装），去重后排序返回。
    非 Windows 平台返回空列表。
    """
    if sys.platform != "win32":
        return []

    try:
        import winreg
    except ImportError:
        return []

    cjk_names: list[str] = []
    seen: set[str] = set()

    for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            key = winreg.OpenKey(
                hive,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts",
            )
            i = 0
            while True:
                try:
                    display_name, filename, _ = winreg.EnumValue(key, i)
                    i += 1
                    filename_lower = filename.lower()
                    if any(kw in filename_lower for kw in CJK_KEYWORDS):
                        clean = _strip_font_type_suffix(display_name)
                        if clean and clean not in seen:
                            seen.add(clean)
                            cjk_names.append(clean)
                except OSError:
                    break
            winreg.CloseKey(key)
        except OSError:
            continue

    cjk_names.sort(key=str.lower)
    return cjk_names


async def check_cjk_fonts() -> dict:
    """检测系统 CJK 字体是否可用。

    Windows 上检查系统字体目录；其他平台跳过（Docker 中通过 fc-list 检查）。

    Returns:
        {"available": bool, "fonts": list[str], "warning": str | None}
    """
    if sys.platform != "win32":
        # 非 Windows 平台：假设 Docker 环境已安装字体
        return {"available": True, "fonts": [], "warning": None}

    windir = os.environ.get("WINDIR", r"C:\Windows")
    fonts_dir = Path(windir) / "Fonts"
    cjk_fonts: list[str] = []

    if fonts_dir.exists():
        for f in fonts_dir.iterdir():
            if f.suffix.lower() in (".ttf", ".ttc", ".otf"):
                name_lower = f.name.lower()
                if any(kw in name_lower for kw in CJK_KEYWORDS):
                    cjk_fonts.append(f.name)

    warning = None
    if not cjk_fonts:
        warning = (
            "未检测到 CJK 字体！弹幕中的中文将无法显示。"
            "请安装 Noto Sans CJK 或微软雅黑字体。"
        )
        logger.warning(warning)

    return {
        "available": bool(cjk_fonts),
        "fonts": cjk_fonts,
        "warning": warning,
    }
