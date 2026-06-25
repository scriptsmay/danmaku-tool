"""CJK 字体可用性检测（Windows）。"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

CJK_KEYWORDS = ["msyh", "simhei", "simsun", "noto", "source han", "wenquanyi", "dengxian"]


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
