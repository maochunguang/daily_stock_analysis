# -*- coding: utf-8 -*-
"""
patch 0003: NEWS_INTEL_ALLOW_PRIVATE_HOSTS 门控测试

自建资讯源（如本机 TrendRadar 的 RSS 输出）需要允许指向内网/本机地址。
默认关闭时保留 SSRF 防护；开启后 localhost / 内网 IP 地址可用。
"""

import unittest
from unittest.mock import MagicMock

from src.services.intelligence_service import (
    IntelligenceService,
    IntelligenceServiceError,
)


class _StubConfig:
    def __init__(self, allow_private: bool):
        self.news_intel_allow_private_hosts = allow_private


def _service(allow_private: bool) -> IntelligenceService:
    return IntelligenceService(repository=MagicMock(), config=_StubConfig(allow_private))


class TestIntelPrivateHostGate(unittest.TestCase):
    """URL 私网地址校验受 news_intel_allow_private_hosts 门控。"""

    def test_private_ip_blocked_by_default(self):
        with self.assertRaises(IntelligenceServiceError):
            _service(False)._validate_url("http://127.0.0.1:9000/trendradar/rss")

    def test_private_ip_allowed_when_enabled(self):
        _service(True)._validate_url("http://127.0.0.1:9000/trendradar/rss")

    def test_localhost_allowed_when_enabled(self):
        _service(True)._validate_url("http://localhost:8080/rss.xml")

    def test_lan_address_allowed_when_enabled(self):
        _service(True)._validate_url("http://192.168.1.10:8080/rss.xml")

    def test_config_gate_defaults_to_closed(self):
        from src.config import get_config

        self.assertFalse(
            bool(getattr(get_config(), "news_intel_allow_private_hosts", False))
        )

    def test_invalid_url_still_rejected_when_enabled(self):
        with self.assertRaises(IntelligenceServiceError):
            _service(True)._validate_url("ftp://127.0.0.1/rss")
        with self.assertRaises(IntelligenceServiceError):
            _service(True)._validate_url("not-a-url")


if __name__ == "__main__":
    unittest.main()
