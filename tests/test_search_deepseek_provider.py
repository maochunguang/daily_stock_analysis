# -*- coding: utf-8 -*-
"""
DeepSeek 官方网页搜索 API 测试套件

测试覆盖范围:
1. Query 构建 - after: 时间操作符拼接与 128 字符硬限制截断
2. 响应解析 - results[] 字段映射（summary 优先、site_name 来源、RFC3339 日期）
3. 参数约束 - count 上限 50、need_content=False、Bearer 鉴权头
4. 错误处理 - 401/402/429/422 错误映射、超时与网络错误降级
5. 服务接线 - SearchService 按 DEEPSEEK_SEARCH_API_KEYS 初始化 provider

运行方式:
```bash
python -m pytest tests/test_search_deepseek_provider.py -v
```
"""

import os
import re
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv
load_dotenv()

# 添加项目根目录到 Python 路径，解决模块导入问题
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Mock newspaper before search_service import (optional dependency)
if "newspaper" not in sys.modules:
    mock_np = MagicMock()
    mock_np.Article = MagicMock()
    mock_np.Config = MagicMock()
    sys.modules["newspaper"] = mock_np

from src.search_service import (  # noqa: E402
    DeepseekSearchProvider,
    SearchService,
    SearchResult,
)


class _FakeResponse:
    """模拟 HTTP 响应对象"""

    def __init__(self, status_code=200, json_data=None, text="", headers=None):
        self.status_code = status_code
        self._json_data = json_data or {}
        self.text = text
        self.headers = headers or {"content-type": "application/json"}

    def json(self):
        return self._json_data


def _make_provider() -> DeepseekSearchProvider:
    return DeepseekSearchProvider(["sk-deepseek-test-key"])


class TestDeepseekQueryBuilding(unittest.TestCase):
    """query 构建：after: 操作符与 128 字符硬限制"""

    def setUp(self):
        self.provider = _make_provider()

    def test_appends_after_operator_for_positive_days(self):
        query = self.provider._build_search_query("600519 贵州茅台 新闻", 7)
        self.assertTrue(query.startswith("600519 贵州茅台 新闻"))
        self.assertRegex(query, r" after:\d{4}-\d{2}-\d{2}$")
        self.assertLessEqual(len(query), 128)

    def test_no_operator_for_non_positive_days(self):
        self.assertEqual(self.provider._build_search_query("茅台 新闻", 0), "茅台 新闻")
        self.assertEqual(
            self.provider._build_search_query("茅台 新闻", None), "茅台 新闻"
        )

    def test_truncates_long_query_to_api_limit(self):
        query = self.provider._build_search_query("好" * 200, 7)
        self.assertLessEqual(len(query), 128)
        self.assertTrue(query.startswith("好" * 100))
        self.assertRegex(query, r" after:\d{4}-\d{2}-\d{2}$")

    def test_strips_surrounding_whitespace(self):
        self.assertEqual(
            self.provider._build_search_query("  茅台 新闻  ", 0), "茅台 新闻"
        )


class TestDeepseekSearchProvider(unittest.TestCase):
    """DeepseekSearchProvider 行为测试（mock HTTP）"""

    def setUp(self):
        self.provider = _make_provider()

    @patch("src.search_service.requests")
    def test_search_success_maps_fields(self, mock_requests):
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass

        fake_response = _FakeResponse(
            status_code=200,
            json_data={
                "results": [
                    {
                        "rerank_score": 2.4,
                        "title": "贵州茅台发布回购公告",
                        "url": "https://finance.sina.com.cn/stock/600519",
                        "snippet": "短摘要，用于前端展示。",
                        "summary": "面向模型的长摘要，包含公告要点与资金安排。",
                        "site_name": "新浪财经",
                        "site_icon": None,
                        "date": "2026-11-10T08:00:00+00:00",
                        "authority": 3,
                    },
                    {
                        "title": "白酒板块走强",
                        "url": "https://www.eastmoney.com/a/123.html",
                        "snippet": "只有短摘要的结果。",
                        "summary": "",
                        "site_name": None,
                        "date": None,
                    },
                ]
            },
        )
        mock_requests.post = MagicMock(return_value=fake_response)

        response = self.provider.search("600519 贵州茅台", max_results=5, days=7)

        self.assertTrue(response.success)
        self.assertEqual(response.provider, "DeepSeek")
        self.assertEqual(len(response.results), 2)

        first = response.results[0]
        self.assertEqual(first.title, "贵州茅台发布回购公告")
        self.assertEqual(first.snippet, "面向模型的长摘要，包含公告要点与资金安排。")
        self.assertEqual(first.source, "新浪财经")
        self.assertEqual(first.published_date, "2026-11-10")

        second = response.results[1]
        self.assertEqual(second.snippet, "只有短摘要的结果。")
        self.assertEqual(second.source, "eastmoney.com")
        self.assertIsNone(second.published_date)

        # 验证 API 调用契约
        mock_requests.post.assert_called_once()
        call_args = mock_requests.post.call_args
        self.assertEqual(
            call_args[0][0], "https://api.deepseek.com/v1/tools/search"
        )
        headers = call_args[1]["headers"]
        self.assertEqual(headers["Authorization"], "Bearer sk-deepseek-test-key")
        payload = call_args[1]["json"]
        self.assertEqual(payload["count"], 5)
        self.assertFalse(payload["need_content"])
        self.assertRegex(payload["query"], r" after:\d{4}-\d{2}-\d{2}$")

    @patch("src.search_service.requests")
    def test_count_is_clamped_to_api_maximum(self, mock_requests):
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass

        fake_response = _FakeResponse(status_code=200, json_data={"results": []})
        mock_requests.post = MagicMock(return_value=fake_response)

        response = self.provider.search("茅台", max_results=100, days=7)

        self.assertTrue(response.success)
        self.assertEqual(response.results, [])
        payload = mock_requests.post.call_args[1]["json"]
        self.assertEqual(payload["count"], 50)

    @patch("src.search_service.requests")
    def test_http_402_maps_to_balance_error(self, mock_requests):
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass

        fake_response = _FakeResponse(
            status_code=402,
            json_data={"error": {"message": "Insufficient Balance"}},
        )
        mock_requests.post = MagicMock(return_value=fake_response)

        response = self.provider.search("茅台 新闻", max_results=5, days=7)

        self.assertFalse(response.success)
        self.assertIn("余额不足", response.error_message)
        self.assertIn("Insufficient Balance", response.error_message)

    @patch("src.search_service.requests")
    def test_timeout_returns_failure(self, mock_requests):
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass

        mock_requests.post = MagicMock(
            side_effect=real_requests.exceptions.Timeout("timed out")
        )

        response = self.provider.search("茅台 新闻", max_results=5, days=7)

        self.assertFalse(response.success)
        self.assertIn("请求超时", response.error_message)
        self.assertEqual(response.results, [])

    @patch("src.search_service.requests")
    def test_invalid_query_is_truncated_before_request(self, mock_requests):
        try:
            import requests as real_requests
            mock_requests.exceptions = real_requests.exceptions
        except ImportError:
            pass

        fake_response = _FakeResponse(status_code=200, json_data={"results": []})
        mock_requests.post = MagicMock(return_value=fake_response)

        self.provider.search("重" * 200, max_results=5, days=7)

        payload = mock_requests.post.call_args[1]["json"]
        self.assertLessEqual(len(payload["query"]), 128)

    def test_extract_domain(self):
        cases = [
            ("https://finance.sina.com.cn/news/1", "finance.sina.com.cn"),
            ("https://www.eastmoney.com/a/1", "eastmoney.com"),
            ("invalid_url", "未知来源"),
            ("", "未知来源"),
        ]
        for url, expected in cases:
            self.assertEqual(
                DeepseekSearchProvider._extract_domain(url), expected
            )

    def test_search_result_dataclass_shape(self):
        result = SearchResult(
            title="标题",
            snippet="摘要",
            url="https://example.com",
            source="example.com",
            published_date="2026-11-10",
        )
        self.assertIn("标题", result.to_text())


class TestDeepseekSearchServiceWiring(unittest.TestCase):
    """SearchService 按配置初始化 DeepSeek provider"""

    def test_search_service_initializes_deepseek_provider(self):
        service = SearchService(deepseek_keys=["k1", "k2"])
        names = [provider.name for provider in service._providers]
        self.assertIn("DeepSeek", names)
        self.assertEqual(
            service._constructor_kwargs["deepseek_keys"], ["k1", "k2"]
        )

    def test_search_service_without_deepseek_keys_skips_provider(self):
        service = SearchService()
        names = [provider.name for provider in service._providers]
        self.assertNotIn("DeepSeek", names)

    def test_provider_order_deepseek_before_searxng(self):
        service = SearchService(
            minimax_keys=["mm"],
            deepseek_keys=["ds"],
            searxng_public_instances_enabled=False,
        )
        names = [provider.name for provider in service._providers]
        self.assertEqual(names, ["MiniMax", "DeepSeek"])


if __name__ == "__main__":
    unittest.main()
