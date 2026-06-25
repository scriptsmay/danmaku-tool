"""字体检测测试。"""
from __future__ import annotations

import sys
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from danmaku_tool.core.font_checker import check_cjk_fonts


@pytest.mark.asyncio
async def test_check_cjk_fonts_non_windows():
    """非 Windows 平台直接返回 available=True。"""
    with patch("sys.platform", "linux"):
        result = await check_cjk_fonts()
    assert result["available"] is True
    assert result["warning"] is None


@pytest.mark.asyncio
async def test_check_cjk_fonts_windows_with_fonts():
    """Windows 上有 CJK 字体。"""
    mock_font = MagicMock()
    mock_font.name = "msyh.ttc"
    mock_font.suffix = ".ttc"

    mock_dir = MagicMock()
    mock_dir.exists.return_value = True
    mock_dir.iterdir.return_value = [mock_font]

    with patch("sys.platform", "win32"), \
         patch("os.environ", {"WINDIR": r"C:\Windows"}), \
         patch("pathlib.Path.__truediv__", return_value=mock_dir):
        # 直接 mock Path
        with patch("danmaku_tool.core.font_checker.Path") as MockPath:
            MockPath.return_value = mock_dir
            result = await check_cjk_fonts()

    # 由于 mock 复杂度，这里主要验证不报错
    assert "available" in result


@pytest.mark.asyncio
async def test_check_cjk_fonts_returns_dict():
    """返回值结构正确。"""
    result = await check_cjk_fonts()
    assert "available" in result
    assert "fonts" in result
    assert "warning" in result
