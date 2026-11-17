# -*- coding: utf-8 -*-
"""
DeepSeek 搜索配置的 registry 注册测试

验证 DEEPSEEK_SEARCH_API_KEYS 在系统配置 schema 中被注册为 data_source 类
（而不是被 ``DEEPSEEK_`` 前缀推断成 ai_model），并复用搜索密钥的多值密码输入。

运行方式:
```bash
python -m pytest tests/test_deepseek_search_registry.py -v
```
"""

import os
import sys
import unittest
from pathlib import Path

project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from src.core.config_registry import (  # noqa: E402
    build_schema_response,
    get_field_definition,
    get_registered_field_keys,
)


class TestDeepseekSearchRegistry(unittest.TestCase):
    """DEEPSEEK_SEARCH_API_KEYS 的 schema 注册行为"""

    def test_field_is_registered_as_data_source(self):
        field = get_field_definition("DEEPSEEK_SEARCH_API_KEYS")
        self.assertEqual(field["category"], "data_source")
        self.assertNotEqual(field["display_order"], 9000)
        self.assertEqual(field["display_order"], 55)

    def test_field_uses_password_multivalue_control(self):
        field = get_field_definition("DEEPSEEK_SEARCH_API_KEYS")
        self.assertEqual(field["ui_control"], "password")
        self.assertTrue(field["is_sensitive"])
        self.assertTrue(field["validation"].get("multi_value"))
        self.assertEqual(field["validation"].get("delimiter"), ",")

    def test_field_has_search_help_and_docs(self):
        field = get_field_definition("DEEPSEEK_SEARCH_API_KEYS")
        self.assertEqual(field["help_key"], "settings.data_source.search_api_keys")
        docs = field.get("docs") or []
        self.assertTrue(
            any("deepseek" in (doc.get("href") or "").lower() for doc in docs)
        )

    def test_schema_response_includes_deepseek_search(self):
        schema = build_schema_response()
        categories = schema.get("categories") or []
        data_source = next(
            (
                category
                for category in categories
                if category.get("category") == "data_source"
            ),
            None,
        )
        self.assertIsNotNone(data_source)
        keys = {
            item.get("key")
            for item in (data_source.get("fields") or [])
            if isinstance(item, dict)
        }
        self.assertIn("DEEPSEEK_SEARCH_API_KEYS", keys)

    def test_llm_key_and_search_key_are_registered_separately(self):
        keys = get_registered_field_keys()
        self.assertIn("DEEPSEEK_API_KEYS", keys)
        self.assertIn("DEEPSEEK_SEARCH_API_KEYS", keys)


if __name__ == "__main__":
    unittest.main()
