from typing import List
from typing import Optional

from bs4 import BeautifulSoup, Tag


class HTMLParserUtil:
    def __init__(self, html_content: str):
        self.soup = BeautifulSoup(html_content, 'html.parser')

    def extract(
            self,
            tag_name: str,
            attr_name: Optional[str] = None,
            search_str: Optional[str] = None,
            match_mode: Optional[str] = None
    ) -> List[str]:
        """
        通用HTML内容提取方法
        :param tag_name: 要查找的标签名称
        :param attr_name: 属性名称（可选）
        :param search_str: 属性值匹配字符串（可选）
        :param match_mode: 匹配模式：'start'/'contains'/'end'/'exact'（可选）
        返回结果列表保持HTML原始顺序
        """
        # 构建CSS选择器
        selector = self._build_selector(tag_name, attr_name, search_str, match_mode)

        # 查找所有匹配元素
        elements = self.soup.select(selector) if selector else self.soup.find_all(tag_name)

        # 提取内容
        return [self._extract_content(element, tag_name, attr_name) for element in elements]

    def _build_selector(
            self,
            tag_name: str,
            attr_name: Optional[str],
            search_str: Optional[str],
            match_mode: Optional[str]
    ) -> Optional[str]:
        """构建CSS选择器"""
        if not attr_name or not search_str:
            return None

        operators = {
            'start': '^=',
            'end': '$=',
            'contains': '*=',
            'exact': '='
        }
        operator = operators.get(match_mode, '*=') if match_mode else '='

        return f"{tag_name}[{attr_name}{operator}'{search_str}']"

    def _extract_content(self, element: Tag, tag_name: str, attr_name: Optional[str]) -> str:
        """根据标签类型提取内容"""
        # 自闭合标签或需要返回属性的情况
        if element.name in ('img', 'input', 'meta'):
            return element.get(attr_name, '') if attr_name else ''

        # 提取完整内部HTML（不包含自身标签）
        return ''.join(str(child) for child in element.contents).strip()

    @property
    def original_order(self) -> List[Tag]:
        """获取原始顺序的所有元素（调试用）"""
        return self.soup.find_all()

    @staticmethod
    def join_results(results: List[str], separator: str = "") -> str:
        """
        将提取结果列表合并为单个字符串
        :param results: extract方法返回的结果列表
        :param separator: 连接符（默认无间隔）
        :return: 合并后的完整字符串
        """
        return separator.join(results)
