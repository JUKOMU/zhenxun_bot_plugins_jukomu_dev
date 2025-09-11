import asyncio
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
            client.login(user, pwd)
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
        创建包含搜索结果信息的图片。
        布局为4列列表，列优先排序，每项包含封面、ID、标题和标签。
        """
        search_page_detail = await self.get_page_info()
        if not search_page_detail or not search_page_detail.get_albums():
            logger.error("没有专辑信息可供生成图片。")
            return None

        # --- 1. 参数配置 ---
        # 布局与尺寸
        COVER_SIZE = (150, 200)  # 封面尺寸 (宽, 高)
        TEXT_AREA_WIDTH = 500  # 文本区域宽度
        ITEM_WIDTH = COVER_SIZE[0] + TEXT_AREA_WIDTH  # 单个项目总宽度
        ITEM_HEIGHT = COVER_SIZE[1]  # 单个项目总高度
        COLS = 4  # 列数
        ITEMS_PER_COL = 20  # 每列最大项目数
        COLUMN_SPACING = 50  # 列间距
        ROW_SPACING = 30  # 项目垂直间距
        PADDING = 100  # 画布四周内边距
        FOOTER_HEIGHT = 120  # 底部页码区域高度

        # 背景颜色和圆角半径
        GLOBAL_BG_COLOR = (0, 0, 0, 20)  # 全局大背景颜色 (浅灰, 半透明)
        ITEM_BG_COLOR = (0, 0, 0, 30)  # 单个项目背景颜色 (白色, 更透明)
        GLOBAL_BG_RADIUS = 30  # 全局背景圆角半径
        ITEM_BG_RADIUS = 20  # 项目背景圆角半径

        # 字体颜色
        FONT_COLOR = (0, 0, 0)
        ID_FONT_COLOR = (80, 80, 80)
        TAGS_FONT_COLOR = (20, 90, 180)
        PAGE_FONT_COLOR = (10, 115, 212)

        # --- 2. 文本截断辅助函数 ---
        def _get_title_lines(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
            """将标题处理为最多两行，第二行超长则截断。"""
            lines = []
            ellipsis = "..."
            ellipsis_width = font.getlength(ellipsis)
            if font.getlength(text) <= max_width:
                return [text]

            first_line_end_index = 0
            for i, char in enumerate(text):
                if font.getlength(text[:i + 1]) > max_width:
                    first_line_end_index = i
                    break

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
            如果文本超过最大宽度，则截断并添加省略号。
            """
            if font.getlength(text) <= max_width:
                return text

            ellipsis = "..."
            ellipsis_width = font.getlength(ellipsis)

            # 从末尾开始逐字削减，直到能容纳省略号
            for i in range(len(text) - 1, 0, -1):
                truncated = text[:i]
                if font.getlength(truncated) + ellipsis_width <= max_width:
                    return truncated + ellipsis

            # 如果连一个字符都放不下，就只返回省略号
            return ellipsis

        # --- 3. 计算画布尺寸与创建画布 ---
        content_width = (ITEM_WIDTH * COLS) + (COLUMN_SPACING * (COLS - 1))
        content_height = (ITEM_HEIGHT * ITEMS_PER_COL) + (ROW_SPACING * (ITEMS_PER_COL - 1))

        canvas_width = content_width + 2 * PADDING
        canvas_height = content_height + PADDING + FOOTER_HEIGHT  # 顶部 PADDING + 内容区 + 底部页码区

        # 加载背景并缩放到目标尺寸
        try:

            canvas_base = Image.open(
                os.path.dirname(os.path.abspath(__file__)) + "/jmcomic_favourite_background.png").convert("RGBA")
            canvas_base = canvas_base.resize((canvas_width, canvas_height), Image.Resampling.LANCZOS)
        except FileNotFoundError:
            logger.error("背景图片 'jmcomic_favourite_background.png' 未找到，使用纯白背景。")
            canvas_base = Image.new("RGBA", (canvas_width, canvas_height), (255, 255, 255, 255))

        # 创建透明绘图层
        canvas = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # --- 4. 加载字体 ---
        try:
            # 字体大小可以根据视觉效果微调
            id_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 36)
            title_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 20)
            tags_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 22)
            page_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/baibaipanpanwudikeai.ttf", 97)
        except IOError:
            logger.error("字体文件加载失败，将使用默认字体。")
            id_font = title_font = tags_font = page_font = ImageFont.load_default()

        # --- 5. 绘制全局背景 ---
        # 计算全局背景的位置和尺寸，它应该包裹住所有的项目
        global_bg_x0 = PADDING - 25  # 比内容区稍微宽一点
        global_bg_y0 = PADDING - 25  # 比内容区稍微高一点
        global_bg_x1 = global_bg_x0 + content_width + 50
        global_bg_y1 = global_bg_y0 + content_height + 50

        draw.rounded_rectangle(
            (global_bg_x0, global_bg_y0, global_bg_x1, global_bg_y1),
            radius=GLOBAL_BG_RADIUS,
            fill=GLOBAL_BG_COLOR
        )

        # --- 6. 循环绘制所有项目 ---
        albums = search_page_detail.get_albums()
        for index, album in enumerate(albums):
            # 计算当前项目所在的行列 (列优先)
            col = index // ITEMS_PER_COL
            row = index % ITEMS_PER_COL

            # 计算当前项目的左上角坐标
            item_x = PADDING + col * (ITEM_WIDTH + COLUMN_SPACING)
            item_y = PADDING + row * (ITEM_HEIGHT + ROW_SPACING)

            # --- 绘制单个项目背景 ---
            # 背景需要稍微比项目内容大一点点，形成边框效果
            item_bg_x0 = item_x - 10
            item_bg_y0 = item_y - 10
            item_bg_x1 = item_x + ITEM_WIDTH + 10
            item_bg_y1 = item_y + ITEM_HEIGHT + 10

            draw.rounded_rectangle(
                (item_bg_x0, item_bg_y0, item_bg_x1, item_bg_y1),
                radius=ITEM_BG_RADIUS,
                fill=ITEM_BG_COLOR
            )

            # 绘制封面
            try:
                cover_img = Image.open(BytesIO(album.get_cover())).convert("RGB").resize(COVER_SIZE)
                canvas.paste(cover_img, (item_x, item_y))
            except Exception as e:
                # 封面加载失败时显示红色占位
                logger.error(f"警告: 封面加载失败 for {album.get_album_id()}. Error: {e}")
                placeholder = Image.new('RGB', COVER_SIZE, (255, 80, 80))
                draw_placeholder = ImageDraw.Draw(placeholder)
                draw_placeholder.text((10, 10), "Cover\nFailed", fill=(255, 255, 255))
                canvas.paste(placeholder, (item_x, item_y))

            # --- 绘制右侧文本信息 ---
            text_x = item_x + COVER_SIZE[0] + 20  # 封面右侧+20px间距
            text_max_width = TEXT_AREA_WIDTH - 40  # 文本区域宽度-左右边距
            current_y = item_y + 15  # 文本起始Y坐标

            # 绘制 Album ID
            draw.text((text_x, current_y), album.get_album_id(), font=id_font, fill=ID_FONT_COLOR)
            current_y += id_font.size + 20  # 增加行距

            # 绘制 Title (截断)
            title_lines = _get_title_lines(album.get_title(), title_font, text_max_width)
            for line in title_lines:
                draw.text((text_x, current_y), line, font=title_font, fill=FONT_COLOR)
                current_y += title_font.size * 2  # 使用固定的行高

            current_y += 5  # 标题和标签之间的额外间距

            # 绘制 Tags (合并后截断)
            tags_str = " / ".join(album.get_tags())
            if not tags_str:
                tags_str = "无标签"
            truncated_tags = _truncate_text(tags_str, tags_font, text_max_width)
            draw.text((text_x, current_y), truncated_tags, font=tags_font, fill=TAGS_FONT_COLOR)

        # --- 7. 绘制页脚页码 ---
        page_text = f"{self.page} / {self.max_page}"
        page_text_length = page_font.getlength(page_text)
        page_x = (canvas_width - page_text_length) // 2  # 水平居中
        page_y = canvas_height - FOOTER_HEIGHT + (FOOTER_HEIGHT - page_font.size) // 2 + 10  # 垂直居中于页脚区域

        draw.text((page_x, page_y), page_text, font=page_font, fill=PAGE_FONT_COLOR)

        # --- 8. 合成并返回 ---

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
