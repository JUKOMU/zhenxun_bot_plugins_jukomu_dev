import asyncio
import os
import re
from io import BytesIO
from pathlib import Path
from typing import Any

import requests
from PIL import Image, ImageDraw, ImageFont
from jmcomic import JmHtmlClient, JmApiClient, JmOption
from requests import Response
from zhenxun.services.log import logger

from .util import HTMLParserUtil

# 每页收藏夹最大本子数量
MAX_ALBUM_NUMBER = 20
# 用于解析各种数据的html
HTML_FOR_DATA = ""
# 基础路径
BASE_PATH = "resources/image/jm_favourite"


def handle_request(url: str, method: str, **args: Any) -> Response:
    try:
        if method == "GET":
            return requests.get(url, **args)
        if method == "POST":
            return requests.post(url, **args)
    except requests.exceptions.RequestException as e:
        logger.error(f"请求失败: {e}")


class AlbumDetail:
    """
    本子详细信息
    :param album_id: 本子jm号
    :param title: 本子标题
    :param cover: 本子封面
    """
    album_id: str
    title: str
    cover: bytes | Any

    def __init__(self, album_id: str, title: str, cover: bytes | Any):
        self.album_id = album_id
        self.title = title
        self.cover = cover

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

    def get_cover(self):
        return self.cover


class FavouritePageDetail:
    """
    收藏夹所有本子详细信息
    """
    albums: list[AlbumDetail]

    def __init__(self):
        self.albums = []

    def add_album(self, album_id: str, title: str, cover: bytes | Any):
        self.albums.append(AlbumDetail(album_id, title, cover))

    def __repr__(self) -> str:
        return f"FavouritePageDetail(albums={self.albums})"

    def __str__(self) -> str:
        if not self.albums:
            return "Empty Favourite Page"

        album_list = "\n".join(f"  → {str(album)}" for album in self.albums)
        return f"Favourite Collection ({len(self.albums)} albums):\n{album_list}"

    def get_albums(self):
        return self.albums


class JmFavouritePage:

    def __init__(self,
                 uid: str,
                 page: int,
                 jm_username: str,
                 jm_password: str):
        """
        JmFavouritePage 初始化
        :param uid: 用户uid QQ号
        :param page: 页码
        :param jm_username: 用户账号
        :param jm_password: 密码
        """
        self.uid: str = uid
        self.page: int = page
        # 用户账号
        self.jm_username: str = jm_username
        # 密码
        self.jm_password: str = jm_password
        # 最大页码
        self.max_page: int = 0
        # JM等级称号
        self.appellation: str = ""
        # JM等级
        self.level: int = 0
        # JM等级进度
        self.exp: str = ""
        # J Coins
        self.jcoins: int = 0
        # xp 分布(战斗力)
        self.xp_power: dict[str, int] = {}
        # QQ头像
        self.avatar: bytes = None
        # client
        self.client: JmHtmlClient | JmApiClient = None

    async def preparation(self):
        option = JmOption.default()
        self.client = option.new_jm_client(impl="html")
        self.client.login(self.jm_username, self.jm_password)
        resp = self.client.get_jm_html(
            f'/user/{self.jm_username}/favorite/albums',
            params={
                'page': 1,
            })
        global HTML_FOR_DATA
        HTML_FOR_DATA = resp.text
        self.max_page = await self.get_max_page()
        if self.max_page >= self.page:
            resp = self.client.get_jm_html(
                f'/user/{self.jm_username}/favorite/albums',
                params={
                    'page': self.page,
                })
            HTML_FOR_DATA = resp.text

    async def async_init(self):
        await self.preparation()
        self.appellation = await self.get_appellation()
        self.level = await self.get_level()
        self.exp = await self.get_exp()
        self.jcoins = await self.get_jcoins()
        self.xp_power = await self.get_xp_power()
        return self

    def __repr__(self) -> str:
        attrs = [
            f"uid={self.uid!r}",
            f"page={self.page}",
            f"max_page={self.max_page}",
            f"appellation={self.appellation!r}",
            f"level={self.level}",
            f"exp={self.exp!r}",
            f"jcoins={self.jcoins}",
            f"xp_power={self.xp_power!r}",
        ]
        return f"JmFavouritePage({', '.join(attrs)})"

    def __str__(self) -> str:
        return (
            f"JmFavouritePage 详细信息:\n"
            f"├─ 用户UID: {self.uid}\n"
            f"├─ 当前页码: {self.page} (最大页码: {self.max_page})\n"
            f"├─ 等级信息: {self.appellation} [Lv.{self.level}]\n"
            f"├─ 经验进度: {self.exp}\n"
            f"├─ J币余额: {self.jcoins:,}\n"
            f"└─ 战力分布: {self._format_xp_power()}"
        )

    def _format_xp_power(self) -> str:
        """格式化战斗力分布"""
        if not self.xp_power:
            return "无数据"
        return "/".join(f"{k}={v}" for k, v in self.xp_power.items())

    def set_avatar(self, avatar: bytes):
        self.avatar = avatar

    async def get_max_page(self) -> int:
        """
        获取最大页码
        """
        parser = HTMLParserUtil(HTML_FOR_DATA)
        # 包含页码的html
        pagination = parser.extract("ul", "class", "pagination", 'exact')
        pagination = parser.join_results(pagination)
        # 页码列表
        page_number_list = HTMLParserUtil(pagination).extract("a", "href", "?page=", 'contains')
        # 获取最大页码
        max_page_number = max(int(s) for s in page_number_list if s.isdigit())
        return max_page_number

    async def get_appellation(self) -> str:
        """
        获取用户JM账户的等级称号
        """
        html_list = await self.get_profile_html()
        for html in html_list:
            if "称号" in html:
                parse = HTMLParserUtil(html)
                appellation = parse.extract("div", "class", "header-profile-row-value", 'contains')[0]
                appellation = appellation.split(" ")[0]
                appellation = re.sub(r'\s+', '', appellation)
                if appellation.find("<!--") > 0:
                    appellation = appellation[:appellation.find("<!--")]
                    return appellation
                return appellation
        return ""

    async def get_level(self) -> int:
        """
        获取用户JM账户的等级
        """
        html_list = await self.get_profile_html()
        for html in html_list:
            if "等级" in html:
                parse = HTMLParserUtil(html)
                level = parse.extract("div", "class", "header-profile-row-value", 'contains')[0]
                level = re.sub(r'\s+', '', level)
                if level.find("<span") > 0:
                    level = level[:level.find("<span")]
                    return int(level)
                return int(level)
        return 0

    async def get_exp(self) -> str:
        """"
        获取用户JM账户的等级进度
        """
        html_list = await self.get_profile_html()
        for html in html_list:
            if "等级" in html:
                parse = HTMLParserUtil(html)
                exp = parse.extract("span", "class", "header-profile-exp", 'contains')[0]
                if exp:
                    return exp
        return ""

    async def get_jcoins(self) -> int:
        """
        获取用户JM账户的J Coins数量
        """
        html_list = await self.get_profile_html()
        for html in html_list:
            if "J Coins" in html:
                parse = HTMLParserUtil(html)
                jcoins = parse.extract("div", "class", "header-profile-row-value", 'contains')[0]
                if jcoins:
                    return int(jcoins)
        return 0

    async def get_xp_power(self) -> dict[str, int]:
        """
        获取用户xp分布
        """
        xp_power: dict[str, int] = {}
        html_list = await self.get_profile_html()
        for html in html_list:
            if ("称号" in html) or ("等级" in html) or ("可收藏数" in html) or ("J Coins" in html) or ("勋章" in html):
                pass
            else:

                parse = HTMLParserUtil(html)
                try:
                    xp_title = parse.extract("div", "class", "header-profile-row-name", 'contains')[0]
                    xp_value = parse.extract("div", "class", "header-profile-row-value", 'contains')[0]
                    if xp_title and xp_value:
                        xp_power[xp_title] = int(xp_value)
                except Exception as e:
                    pass
        return xp_power

    async def get_profile_html(self) -> list[str]:
        """
        用于获取包含用户JM账户profile信息的html
        """
        parser = HTMLParserUtil(HTML_FOR_DATA)
        html_list = parser.extract("div", "class", "header-profile-row", 'exact')
        return html_list

    async def get_cover_data(self, url: str) -> bytes | Any:
        """
        获取封面图片二进制数据
        """
        resp = self.client.get_jm_html(f'/{url}')
        # 添加状态码和内容长度检查
        if resp is None:
            logger.error(f"请求失败: URL={url}")
            return b""
        # print(f"封面请求: URL={url}, 状态码={resp.status_code}, 数据长度={len(resp.content)} bytes")
        # print(self.get_image_info(resp.content))
        return resp.content

    async def get_page_info(self) -> FavouritePageDetail | None:
        """
        获取当前收藏夹的详细信息
        """
        if not self.check():
            return None
        parser = HTMLParserUtil(HTML_FOR_DATA)
        # 包含本子信息的html
        albums = parser.extract("div", "id", "favorites_album_", 'start')
        albums_html = parser.join_results(albums)
        parser = HTMLParserUtil(albums_html)
        # 按html顺序排列的封面
        cover_urls = parser.extract("img", "src", None, None)
        # 按html顺序排列的标题
        titles = parser.extract("div", "class", "video-title", 'contains')
        # 按html顺序排列的album_id
        album_ids = [re.search(r'/albums/(\d+)', album_id).group(1) for album_id in cover_urls]

        async def limited_get(url: str):
            async with asyncio.Semaphore(20):  # 控制同时进行的请求数
                return await self.get_cover_data(url)

        # 创建协程任务列表
        tasks = [limited_get(url) for url in cover_urls]
        # 并发执行所有任务
        cover_datas = await asyncio.gather(*tasks)

        page_detail = FavouritePageDetail()
        for album_id, title, cover_data in zip(album_ids, titles, cover_datas):
            page_detail.add_album(f"JM{album_id}", title, cover_data)

        return page_detail

    def check(self) -> bool:
        """
        检查page的值是否有效
        """
        return self.page <= self.max_page

    async def create_page_img(self):
        """
        创建包含本子信息的图片
        """
        favourite_page_detail = await self.get_page_info()
        if not favourite_page_detail:
            return None

        # 基础参数配置
        AVATAR_SIZE = (369, 369)  # 头像尺寸
        AVATAR_POS = (143, 74)  # 头像位置
        USER_NAME_POS = (619, 52)  # 用户名位置
        LEVEL_POS = (619, 190)  # 等级的位置
        APPELLATION_POS = (619, 292)  # 称号的位置
        JCOIN_POS = (619, 394)  # J Coins的位置
        XP_POWER_TITLE_POS = (2060, 52)  # 战力分布标题位置
        XP_1_POS = (2060, 212)
        XP_2_POS = (2060, 308)
        XP_3_POS = (2060, 404)
        PAGE_POS = (1212, 3900)  # 页码位置
        COVER_SIZE = (400, 533)  # 封面尺寸
        COLS = 5  # 每行数量
        ROWS = 4  # 总行数
        SPACING = 80  # 元素间距
        PADDING = 200  # 画布四周边距
        BG_COLOR = (255, 255, 255)  # 背景色
        FONT_COLOR = (0, 0, 0)  # 字体颜色
        TEXT_MARGIN = 20  # 文字区域左右边距
        ID_HEIGHT = 80  # ID显示区域高度
        PAGE_BANNER_HEIGHT = 130  # 页码区域高度
        HEADER_HEIGHT = 300  # 头部信息区域高度

        # 计算画布尺寸
        cell_width = COVER_SIZE[0]
        cell_height = ID_HEIGHT + COVER_SIZE[1] + 120  # 封面高度 + 标题区域高度

        canvas_width = COLS * cell_width + (COLS - 1) * SPACING + 2 * PADDING
        canvas_height = ROWS * cell_height + (ROWS - 1) * SPACING + 2 * PADDING + PAGE_BANNER_HEIGHT + HEADER_HEIGHT

        # 创建画布
        canvas_base = Image.open(
            os.path.dirname(os.path.abspath(__file__)) + "/jmcomic_favourite_background.png").convert("RGBA")
        draw_base = ImageDraw.Draw(canvas_base, mode='RGBA')
        canvas = Image.new("RGBA", canvas_base.size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(canvas)

        # 加载字体
        title_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 30)
        id_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 42)
        user_title_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/baibaipanpanwudikeai.ttf",
                                             127)
        user_profile_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/baibaipanpanwudikeai.ttf",
                                               77)
        user_xp_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/baibaipanpanwudikeai.ttf", 69)
        page_font = ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/baibaipanpanwudikeai.ttf", 97)

        def smart_wrap(text, max_width, max_lines=4):
            """智能换行函数"""
            lines = []
            current_line = []
            current_width = 0
            ellipsis = '...'
            ellipsis_width = title_font.getlength(ellipsis)

            for char in text:
                char_width = title_font.getlength(char)
                new_width = current_width + char_width

                # 判断是否超出当前行（考虑可能的省略号）
                if new_width > max_width - ellipsis_width:
                    if len(lines) < max_lines - 1:  # 允许换行
                        lines.append(''.join(current_line))
                        current_line = [char]
                        current_width = char_width
                    else:  # 最后一行处理
                        # 计算剩余可用空间（考虑省略号）
                        remaining = max_width - current_width
                        if remaining >= ellipsis_width:
                            current_line.append(ellipsis)
                        else:
                            # 移除部分字符以容纳省略号
                            while current_line and (current_width + ellipsis_width > max_width):
                                removed_char = current_line.pop()
                                current_width -= title_font.getlength(removed_char)
                            current_line.append(ellipsis)
                        break
                else:
                    current_line.append(char)
                    current_width += char_width

            # 处理剩余字符（关键修正点）
            if current_line and len(lines) < max_lines:
                # 仅当有剩余内容且未超过最大行数时添加
                lines.append(''.join(current_line))

            # 删除空行（当实际内容不足时）
            while len(lines) < max_lines:
                lines.append('')  # 填充空行保持结构

            # 去除尾部空行（仅保留实际内容行）
            actual_lines = []
            for line in lines:
                if line.strip():
                    actual_lines.append(line)
                else:
                    break

            # 确保不超过最大行数
            return actual_lines[:max_lines]

        def draw_rounded_rectangle(draw, bbox, radius, fill=None, outline=None):
            """
            绘制圆角矩形
            :param draw: ImageDraw 对象
            :param bbox: 矩形区域 (x0, y0, x1, y1)
            :param radius: 圆角半径（像素）
            :param fill: 填充颜色（支持RGBA）
            :param outline: 边框颜色（支持RGBA）
            """
            x0, y0, x1, y1 = bbox
            height = abs(y1 - y0)

            # 自动调整半径防止过大
            radius = min(radius, height // 2, (x1 - x0) // 2)

            # 绘制四个角的圆弧
            draw.ellipse((x0, y0, x0 + radius * 2, y0 + radius * 2), fill=fill, outline=outline)  # 左上
            draw.ellipse((x1 - radius * 2, y0, x1, y0 + radius * 2), fill=fill, outline=outline)  # 右上
            draw.ellipse((x0, y1 - radius * 2, x0 + radius * 2, y1), fill=fill, outline=outline)  # 左下
            draw.ellipse((x1 - radius * 2, y1 - radius * 2, x1, y1), fill=fill, outline=outline)  # 右下

            # 填充中间区域
            draw.rectangle(
                (x0 + radius, y0, x1 - radius, y1),
                fill=fill,
                outline=outline
            )
            draw.rectangle(
                (x0, y0 + radius, x1, y1 - radius),
                fill=fill,
                outline=outline
            )

        # 遍历所有作品
        for index, album in enumerate(favourite_page_detail.get_albums()):
            # 计算位置
            row = index // COLS
            col = index % COLS
            x = col * (cell_width + SPACING) + PADDING
            y = row * (cell_height + SPACING) + PADDING + HEADER_HEIGHT + 80

            # 计算ID文本位置（居中显示）
            id_text = album.get_album_id()
            id_width = id_font.getlength(id_text)
            id_x = x + (COVER_SIZE[0] - id_width) // 2
            id_y = y + (ID_HEIGHT - id_font.size) // 2

            # 绘制ID文本
            draw.text(
                (id_x, id_y),
                id_text,
                font=id_font,
                fill=(50, 50, 50)  # 深灰色
            )

            # 处理封面
            try:
                cover = Image.open(BytesIO(album.get_cover())).resize(COVER_SIZE)
                canvas.paste(cover, (x, y + ID_HEIGHT))
            except:
                # 封面加载失败时显示红色占位
                cover = Image.new('RGB', COVER_SIZE, (255, 0, 0))
                canvas.paste(cover, (x, y + ID_HEIGHT))

            # 智能换行处理
            max_text_width = COVER_SIZE[0] - 2 * TEXT_MARGIN
            wrapped_lines = smart_wrap(album.get_title(), max_text_width)

            # 绘制文字背景
            text_bg_height = 170
            rect_bbox = (
                x,
                y + COVER_SIZE[1] + ID_HEIGHT,
                x + COVER_SIZE[0],
                y + COVER_SIZE[1] + text_bg_height + ID_HEIGHT
            )
            draw_rounded_rectangle(
                draw=draw,
                bbox=rect_bbox,
                radius=20,
                fill=(0, 0, 0, 20),
                outline=None
            )

            # 绘制文字
            line_height = title_font.size + 5
            for i, line in enumerate(wrapped_lines):
                if not line:  # 跳过空行
                    continue
                text_y = y + COVER_SIZE[1] + ID_HEIGHT + 10 + i * line_height
                draw.text(
                    (x + TEXT_MARGIN, text_y),
                    line,
                    font=title_font,
                    fill=FONT_COLOR
                )

        # 绘制header区域
        # 绘制头像
        try:
            # 尝试加载用户头像
            if self.avatar:
                avatar = Image.open(BytesIO(self.avatar)).resize(AVATAR_SIZE)
            else:
                # 如果没有提供头像数据，直接使用默认
                raise FileNotFoundError("Avatar data is empty")

        except Exception as e:
            logger.error(f"头像加载失败: {str(e)}")
            try:
                # 尝试加载本地默认头像
                avatar = Image.open(os.path.dirname(os.path.abspath(__file__)) + "/avatar.png").resize(AVATAR_SIZE)
            except:
                # 创建纯色替代头像
                avatar = Image.new("RGB", AVATAR_SIZE, (200, 200, 200))  # 浅灰色背景
                draw = ImageDraw.Draw(avatar)
                draw.text(
                    (AVATAR_SIZE[0] // 2 - 40, AVATAR_SIZE[1] // 2 - 20),  # 居中显示
                    "头像缺失",
                    fill=(0, 0, 0),
                    font=ImageFont.truetype(os.path.dirname(os.path.abspath(__file__)) + "/msyh.ttc", 30)
                )

        # 确保坐标是二元组格式
        if isinstance(AVATAR_POS, tuple) and len(AVATAR_POS) == 2:
            canvas.paste(avatar, AVATAR_POS)
        else:
            raise ValueError(f"无效的坐标格式: {AVATAR_POS} (应使用 (x, y) 格式)")

        # 绘制用户名
        draw.text(
            USER_NAME_POS,
            self.jm_username,
            font=user_title_font,
            fill=(0, 0, 0)
        )

        # 绘制等级
        draw.text(
            LEVEL_POS,
            f"Level    {str(self.level)}{self.exp}",
            font=user_profile_font,
            fill=(0, 0, 0)
        )

        # 绘制称号
        draw.text(
            APPELLATION_POS,
            f"称号    {self.appellation}",
            font=user_profile_font,
            fill=(0, 0, 0)
        )

        # 绘制J Coins
        draw.text(
            JCOIN_POS,
            f"J Coins    {str(self.jcoins)}",
            font=user_profile_font,
            fill=(0, 0, 0)
        )

        # 绘制战力分布
        draw.text(
            XP_POWER_TITLE_POS,
            f"战力分布",
            font=user_title_font,
            fill=(0, 0, 0)
        )

        # 绘制XP
        if len(self.xp_power):
            xp1_title = ""
            xp1_value = 0
            # 获取最高的xp
            for key, value in self.xp_power.items():
                if value > xp1_value:
                    xp1_title = key
                    xp1_value = value

            draw.text(
                XP_1_POS,
                f"{xp1_title}  {str(xp1_value)}",
                font=user_xp_font,
                fill=(0, 0, 0)
            )
            if len(self.xp_power) > 1:
                # 获取第二高的xp
                xp2_title = ""
                xp2_value = 0
                self.xp_power.pop(xp1_title)
                for key, value in self.xp_power.items():
                    if value > xp2_value:
                        xp2_title = key
                        xp2_value = value
                draw.text(
                    XP_2_POS,
                    f"{xp2_title}  {str(xp2_value)}",
                    font=user_xp_font,
                    fill=(0, 0, 0)
                )
                if len(self.xp_power) > 1:
                    # 获取第三高的xp
                    xp3_title = ""
                    xp3_value = 0
                    self.xp_power.pop(xp2_title)
                    for key, value in self.xp_power.items():
                        if value > xp3_value:
                            xp3_title = key
                            xp3_value = value
                    draw.text(
                        XP_3_POS,
                        f"{xp3_title}  {str(xp3_value)}",
                        font=user_xp_font,
                        fill=(0, 0, 0)
                    )

        # 绘制页码
        draw.text(
            PAGE_POS,
            f"{self.page}/{self.max_page}",
            font=page_font,
            fill=(10, 115, 212)
        )

        # canvas.show()
        result = Image.alpha_composite(canvas_base, canvas)
        # result.save("output.png")
        return result

    def get_image_info(self, image_data: bytes) -> dict:
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

    @staticmethod
    async def clear_cache(uid: str) -> bool:
        """
        删除已缓存的图片
        图片格式 {uid}_{page}.png
        """
        try:
            for path in os.listdir((Path() / f"{BASE_PATH}").absolute()):
                file_path = os.path.join((Path() / f"{BASE_PATH}").absolute(), path)
                if os.path.isdir(file_path):
                    continue
                if file_path.find(uid) != -1:
                    os.remove(file_path)
        except Exception:
            return False
        return True


if __name__ == '__main__':
    # 测试
    async def main():
        page = await JmFavouritePage("xxx", 3, "xxx", "xxx").async_init()
        if page.check():
            # detail = await page.get_page_info()
            # print(detail)  # 查看结果
            await page.create_page_img()
            # print(page.__str__())


    asyncio.run(main())
