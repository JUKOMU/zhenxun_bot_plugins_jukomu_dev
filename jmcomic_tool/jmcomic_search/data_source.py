import asyncio
import math
import os
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont
from jmcomic import JmOption, JmSearchPage
from requests import Response
from zhenxun.services.log import logger

# 每页搜索最大本子数量
MAX_ALBUM_NUMBER = 80
# 基础路径
BASE_PATH = "resources/image/jm_search"


def handle_request(url: str, method: str, **args: Any) -> Response:
    try:
        if method == "GET":
            return requests.get(url, **args)
        if method == "POST":
            return requests.post(url, **args)
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")


def get_image_info(image_data: bytes) -> dict:
    """
    获取图片信息（支持常见格式）
    """
    try:
        with Image.open(BytesIO(image_data)) as img:
            return {
                "format": img.format,  # 格式（JPEG/PNG等）
                "size": img.size,  # 尺寸 (width, height)
                "mode": img.mode,  # 颜色模式（RGB/RGBA等）
                "info": img.info  # 元数据（如EXIF）
            }
    except Exception as e:
        logger.error(f"解析失败: {str(e)}")
        return {}


class AlbumDetail:
    """
    本子详细信息
    :param album_id: 本子jm号
    :param title: 本子标题
    :param tags: 标签
    :param cover: 本子封面
    """
    album_id: str
    title: str
    tags: list[str]
    cover: bytes | Any

    def __init__(self, album_id: str, title: str, tags: list[str]):
        self.album_id = album_id
        self.title = title
        self.tags = tags

    def __repr__(self) -> str:
        cover_info = f"<bytes, {len(self.cover)} bytes>" if isinstance(self.cover, bytes) else repr(self.cover)
        return f"AlbumDetail(album_id={repr(self.album_id)}, title={repr(self.title)}, cover={cover_info})"

    def __str__(self) -> str:
        cover_size = f"{len(self.cover)} bytes" if isinstance(self.cover, bytes) else "non-bytes data"
        return f"[{self.album_id}]『{self.title}』(Cover: {cover_size})"

    def get_album_id(self):
        return self.album_id

    def get_title(self):
        return self.title

    def get_tags(self):
        return self.tags

    def get_cover(self):
        return self.cover

    def set_cover(self, cover_bytes: bytes | Any):
        self.cover = cover_bytes

    def load_cover(self):
        option = JmOption.default()
        client = option.new_jm_client(impl="html")
        url = f'/media/albums/{self.album_id}_3x4.jpg'
        resp = client.get_jm_html(f'{url}')
        # 添加状态码和内容长度检查
        if resp is None:
            logger.error(f"请求失败: URL={url}")
            self.cover = b""
        self.cover = resp.content


class SearchPageDetail:
    """
    搜索页所有本子详细信息
    """
    albums: list[AlbumDetail]

    def __init__(self):
        self.albums = []

    def add_album(self, album_id: str, title: str, tags: list[str]):
        self.albums.append(AlbumDetail(album_id, title, tags))

    def __repr__(self) -> str:
        return f"SearchPageDetail(albums={self.albums})"

    def __str__(self) -> str:
        if not self.albums:
            return "Empty Search Page"

        album_list = "\n".join(f"  → {str(album)}" for album in self.albums)
        return f"Search Collection ({len(self.albums)} albums):\n{album_list}"

    def get_albums(self):
        return self.albums

    async def load_albums(self):
        # 创建线程池，最大20个线程
        with ThreadPoolExecutor(max_workers=20) as executor:
            # 收集所有任务
            tasks = []
            loop = asyncio.get_event_loop()

            for album in self.albums:
                # 将同步的 load_cover() 方法放到线程池中执行
                task = loop.run_in_executor(
                    executor,
                    album.load_cover  # 注意这里不加括号，不是调用而是传递方法
                )
                tasks.append(task)

            # 等待所有任务完成
            await asyncio.gather(*tasks)


class JmSearchPageManager:
    """
    搜索页管理
    """

    def __init__(self,
                 search_params: list[str],
                 filter_params: list[str],
                 page: int):
        """
        JmSearchPageManager 初始化
        :param search_params: 搜索参数
        :param page: 页码
        """
        self.search_params: list[str] = search_params
        self.filter_params: list[str] = filter_params
        self.page: int = page
        # 当前搜索页结果数量
        self.album_number: int = 0
        # 最大页码
        self.max_page: int = 0
        # JmSearchPage
        self.jm_search_page: JmSearchPage = None
        # SearchPageDetail
        self.search_page_detail: SearchPageDetail = None

    def __repr__(self) -> str:
        attrs = [
            f"search_params={self.search_params!r}",
            f"album_number={self.album_number}",
            f"page={self.page}",
            f"max_page={self.max_page}",
            f"client={self.client!r}",
            f"search_page_detail={self.search_page_detail.__repr__()!r}",
        ]
        return f"JmSearchPageManager({', '.join(attrs)})"

    async def async_init(self):
        """
        初始化
        """
        option = JmOption.default()
        client = option.new_jm_client(impl="html")
        # 账号'xxx'
        user: str | Any = None
        # 密码'xxx'
        pwd: str | Any = None
        if user is None and pwd is None:
            logger.info(f"Jm搜索插件未设置账密,部分受限本子无法搜索")
        else:
            try:
                client.login(user, pwd)
            except Exception:
                pass
        # 构造搜索字符串
        search_str = self.get_search_str()
        # 进行查询
        self.jm_search_page = client.search_site(search_query=search_str, page=self.page)
        # 获取最大页数
        self.max_page = self.jm_search_page.page_count
        # 检查page参数
        if not self.check():
            # 即使page大于最大页数也是有结果的,此时搜索结果为最后一页的数据
            self.page = self.max_page
        # 加载搜索详情
        await self.load_search_page_detail()
        return self

    def get_search_str(self):
        """
        构造搜索字符串
        """
        search_str = ""
        for _str in self.search_params:
            search_str = search_str + "+" + _str + " "
        for _str in self.filter_params:
            if _str != "AI绘图":
                search_str = search_str + "-" + _str + " "
        search_str = search_str + "-" + "AI绘图"
        return search_str.strip()

    async def load_search_page_detail(self):
        """
        加载搜索详情
        """
        self.search_page_detail = SearchPageDetail()
        for aid, title, tags in self.jm_search_page.iter_id_title_tag():
            self.search_page_detail.add_album(album_id=aid, title=title, tags=tags)

    async def get_max_page(self) -> int:
        """
        获取最大页码
        """
        return self.max_page

    async def get_page_info(self) -> SearchPageDetail | None:
        """
        获取当前搜索的详细信息
        """
        await self.search_page_detail.load_albums()
        return self.search_page_detail

    def check(self) -> bool:
        """
        检查page的值是否有效
        """
        return self.page <= self.max_page

    async def create_page_img(self):
        """
        创建包含搜索结果信息的图片
        自适应布局
        动态缩放
        """
        search_page_detail = await self.get_page_info()
        if not search_page_detail or not search_page_detail.get_albums():
            logger.error("没有本子信息可供生成图片。")
            return None

        def resize_and_crop_background(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
            """
            等比例缩放背景图至刚好覆盖目标尺寸，然后居中裁剪。
            """
            target_width, target_height = target_size
            target_ratio = target_width / target_height
            img_width, img_height = img.size
            img_ratio = img_width / img_height
            if img_ratio > target_ratio:
                scale_h = target_height / img_height
                scaled_width, scaled_height = int(img_width * scale_h), target_height
                img = img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                left = (scaled_width - target_width) // 2
                img = img.crop((left, 0, left + target_width, scaled_height))
            else:
                scale_w = target_width / img_width
                scaled_width, scaled_height = target_width, int(img_height * scale_w)
                img = img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                top = (scaled_height - target_height) // 2
                img = img.crop((0, top, scaled_width, top + target_height))
            return img

        def resize_cover_to_fill(img: Image.Image, target_size: tuple[int, int]) -> Image.Image:
            """
            等比例缩放封面图至刚好填满目标尺寸框，然后居中裁剪，确保无拉伸。
            """
            target_width, target_height = target_size
            target_ratio = target_width / target_height
            img_width, img_height = img.size
            img_ratio = img_width / img_height
            if img_ratio > target_ratio:
                scale_h = target_height / img_height
                scaled_width, scaled_height = int(img_width * scale_h), target_height
                img = img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                left = (scaled_width - target_width) // 2
                return img.crop((left, 0, left + target_width, scaled_height))
            else:
                scale_w = target_width / img_width
                scaled_width, scaled_height = target_width, int(img_height * scale_w)
                img = img.resize((scaled_width, scaled_height), Image.Resampling.LANCZOS)
                top = (scaled_height - target_height) // 2
                return img.crop((0, top, scaled_width, top + target_height))

        # 定义基准尺寸和最大布局
        albums = search_page_detail.get_albums()
        num_albums = len(albums)

        BASE_COVER_SIZE = (150, 200)
        BASE_TEXT_AREA_WIDTH = 500
        BASE_ITEM_WIDTH = BASE_COVER_SIZE[0] + BASE_TEXT_AREA_WIDTH
        BASE_ITEM_HEIGHT = BASE_COVER_SIZE[1]
        BASE_ITEMS_PER_COL = 20
        BASE_COLUMN_SPACING = 50
        BASE_ROW_SPACING = 30
        BASE_PADDING = 100
        BASE_FOOTER_HEIGHT = 120
        BASE_ID_FONT_SIZE, BASE_TITLE_FONT_SIZE, BASE_TAGS_FONT_SIZE, BASE_PAGE_FONT_SIZE = 36, 20, 22, 97
        MAX_COLS = 4

        # 计算固定画布尺寸
        max_content_width = (BASE_ITEM_WIDTH * MAX_COLS) + (BASE_COLUMN_SPACING * (MAX_COLS - 1))
        max_content_height = (BASE_ITEM_HEIGHT * BASE_ITEMS_PER_COL) + (BASE_ROW_SPACING * (BASE_ITEMS_PER_COL - 1))
        canvas_width = max_content_width + 2 * BASE_PADDING
        canvas_height = max_content_height + BASE_PADDING + BASE_FOOTER_HEIGHT

        # 寻找最佳布局以最大化缩放
        if num_albums == 0:
            best_layout = (1, 1)
            best_scale_factor = 1.0
        else:
            best_layout = (1, num_albums)
            best_scale_factor = 0.0
            # 遍历所有可能的列数
            for c in range(1, MAX_COLS + 1):
                if c > num_albums: break
                r = math.ceil(num_albums / c)
                if r > BASE_ITEMS_PER_COL: continue  # 避免过于细长的列

                # 计算当前布局(c,r)在基准尺寸下的宽高
                unscaled_w = (BASE_ITEM_WIDTH * c) + (BASE_COLUMN_SPACING * (c - 1))
                unscaled_h = (BASE_ITEM_HEIGHT * r) + (BASE_ROW_SPACING * (r - 1))

                # 计算能让这个布局恰好填满画布的缩放因子
                scale_w = max_content_width / unscaled_w
                scale_h = max_content_height / unscaled_h
                current_scale = min(scale_w, scale_h)

                # 采用能够最大缩放的布局
                if current_scale > best_scale_factor:
                    best_scale_factor = current_scale
                    best_layout = (c, r)

        actual_cols, rows_in_tallest_column = best_layout
        scale_factor = best_scale_factor

        # 应用缩放因子，生成最终尺寸
        COVER_SIZE = (int(BASE_COVER_SIZE[0] * scale_factor), int(BASE_COVER_SIZE[1] * scale_factor))
        TEXT_AREA_WIDTH = int(BASE_TEXT_AREA_WIDTH * scale_factor)
        ITEM_WIDTH = COVER_SIZE[0] + TEXT_AREA_WIDTH
        ITEM_HEIGHT = COVER_SIZE[1]
        COLUMN_SPACING = int(BASE_COLUMN_SPACING * scale_factor)
        ROW_SPACING = int(BASE_ROW_SPACING * scale_factor)
        ID_FONT_SIZE = int(BASE_ID_FONT_SIZE * scale_factor)
        TITLE_FONT_SIZE = int(BASE_TITLE_FONT_SIZE * scale_factor)
        TAGS_FONT_SIZE = int(BASE_TAGS_FONT_SIZE * scale_factor)
        ORDINAL_FONT_SIZE = int(ITEM_HEIGHT * 0.85)  # 新增：序号字体大小

        #  计算居中偏移量
        scaled_content_width = (ITEM_WIDTH * actual_cols) + (COLUMN_SPACING * (actual_cols - 1))
        scaled_content_height = (ITEM_HEIGHT * rows_in_tallest_column) + (ROW_SPACING * (rows_in_tallest_column - 1))
        content_start_x = BASE_PADDING + (max_content_width - scaled_content_width) // 2
        content_start_y = BASE_PADDING + (max_content_height - scaled_content_height) // 2

        # 绘制
        def _get_title_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
            """
            将标题处理为最多两行，第二行超长则截断
            """
            lines, ellipsis = [], "..."
            ellipsis_width = font.getlength(ellipsis)
            if font.getlength(text) <= max_width: return [text]
            first_line_end_index = 0
            for i, char in enumerate(text):
                if font.getlength(text[:i + 1]) > max_width: first_line_end_index = i; break
            lines.append(text[:first_line_end_index])
            second_line_raw = text[first_line_end_index:]
            if font.getlength(second_line_raw) <= max_width:
                lines.append(second_line_raw)
            else:
                truncated_second_line = ""
                for char in second_line_raw:
                    if font.getlength(truncated_second_line + char) <= max_width - ellipsis_width:
                        truncated_second_line += char
                    else:
                        break
                lines.append(truncated_second_line + ellipsis)
            return lines

        def _truncate_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
            """
            如果文本超过最大宽度，则截断并添加省略号
            """
            if font.getlength(text) <= max_width: return text
            ellipsis = "..."
            ellipsis_width = font.getlength(ellipsis)
            for i in range(len(text) - 1, 0, -1):
                if font.getlength(text[:i]) + ellipsis_width <= max_width: return text[:i] + ellipsis
            return ellipsis

        try:
            canvas_base_raw = Image.open(
                os.path.dirname(os.path.abspath(__file__)) + "/jmcomic_favourite_background.png").convert("RGBA")
            canvas_base = resize_and_crop_background(canvas_base_raw, (canvas_width, canvas_height))
        except FileNotFoundError:
            logger.error("背景图片未找到，使用纯白背景。")
            canvas_base = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))

        canvas = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        try:
            font_path = os.path.dirname(os.path.abspath(__file__))
            id_font = ImageFont.truetype(font_path + "/msyh.ttc", ID_FONT_SIZE)
            title_font = ImageFont.truetype(font_path + "/msyh.ttc", TITLE_FONT_SIZE)
            tags_font = ImageFont.truetype(font_path + "/msyh.ttc", TAGS_FONT_SIZE)
            page_font = ImageFont.truetype(font_path + "/baibaipanpanwudikeai.ttf", BASE_PAGE_FONT_SIZE)
            ordinal_font = ImageFont.truetype(font_path + "/msyh.ttc", ORDINAL_FONT_SIZE)  # 新增：加载序号字体
        except IOError:
            logger.error("字体文件加载失败，使用默认字体。")
            id_font = title_font = tags_font = page_font = ordinal_font = ImageFont.load_default()

        draw.rounded_rectangle((BASE_PADDING - 25, BASE_PADDING - 25, BASE_PADDING + max_content_width + 25,
                                BASE_PADDING + max_content_height + 25), radius=30, fill=(0, 0, 0, 20))

        for index, album in enumerate(albums):
            col, row = index // rows_in_tallest_column, index % rows_in_tallest_column
            item_x = content_start_x + col * (ITEM_WIDTH + COLUMN_SPACING)
            item_y = content_start_y + row * (ITEM_HEIGHT + ROW_SPACING)

            draw.rounded_rectangle((item_x - 10, item_y - 10, item_x + ITEM_WIDTH + 10, item_y + ITEM_HEIGHT + 10),
                                   radius=20, fill=(0, 0, 0, 30))

            # 绘制背景序号
            ordinal_text = str(index + 1)
            ordinal_x = item_x + ITEM_WIDTH - int(15 * scale_factor)
            ordinal_y = item_y + ITEM_HEIGHT // 2
            draw.text(
                (ordinal_x, ordinal_y),
                ordinal_text,
                font=ordinal_font,
                fill=(0, 0, 0, 70),  # 使用半透明的深灰色
                anchor="rm"  # 右对齐，垂直居中
            )

            # 绘制封面
            try:
                cover_img_raw = Image.open(BytesIO(album.get_cover())).convert("RGB")
                cover_img = resize_cover_to_fill(cover_img_raw, COVER_SIZE)
                canvas.paste(cover_img, (item_x, item_y))
            except Exception as e:
                logger.error(f"警告: 封面加载失败 for {album.get_album_id()}. Error: {e}")
                placeholder = Image.new('RGB', COVER_SIZE, (255, 80, 80))
                ImageDraw.Draw(placeholder).text((10, 10), "Cover\nFailed", fill=(255, 255, 255))
                canvas.paste(placeholder, (item_x, item_y))
            # 绘制右侧的jm号、标题、标签
            text_x = item_x + COVER_SIZE[0] + int(20 * scale_factor)
            text_max_width = TEXT_AREA_WIDTH - int(40 * scale_factor)
            current_y = item_y + int(15 * scale_factor)
            draw.text((text_x, current_y), album.get_album_id(), font=id_font, fill=(0, 123, 255))
            current_y += id_font.size + int(20 * scale_factor)
            title_lines = _get_title_lines(album.get_title(), title_font, text_max_width)
            for line in title_lines: draw.text((text_x, current_y), line, font=title_font,
                                               fill=(0, 0, 0)); current_y += title_font.size * 2
            current_y += int(5 * scale_factor)
            tags_str = " / ".join(album.get_tags()) or "无标签"
            truncated_tags = _truncate_text(tags_str, tags_font, text_max_width)
            draw.text((text_x, current_y), truncated_tags, font=tags_font, fill=(20, 90, 180))

        # 绘制页脚页码
        page_text = f"{self.page} / {self.max_page}"
        page_text_length = page_font.getlength(page_text)
        page_x = (canvas_width - page_text_length) // 2
        page_y = canvas_height - BASE_FOOTER_HEIGHT + (BASE_FOOTER_HEIGHT - BASE_PAGE_FONT_SIZE) // 2 + 10
        draw.text((page_x, page_y), page_text, font=page_font, fill=(10, 115, 212))

        result = Image.alpha_composite(canvas_base, canvas)
        final_for_show = Image.new("RGB", result.size, (255, 255, 255))
        final_for_show.paste(result, (0, 0), result)

        # result.save("search_output.png") # 用于调试时保存
        return final_for_show


if __name__ == '__main__':
    # 测试
    async def main():
        page = await JmSearchPageManager(search_params=["萝莉", "全彩"], filter_params=["3D", "皮物"],
                                         page=1).async_init()
        print(page.check())
        print(page.max_page)
        print(page.get_search_str())
        await page.create_page_img()


    asyncio.run(main())
