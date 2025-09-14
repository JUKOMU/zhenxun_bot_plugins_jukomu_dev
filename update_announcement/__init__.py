import configparser
import os
import textwrap
import time
from io import BytesIO

from PIL import Image, ImageDraw, ImageFont
from arclet.alconna import Arg
from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna, Match, Target
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .announcement import announcement_type_list, Announcement, AnnouncementType

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.ini')
config = configparser.ConfigParser()

MANAGER_LIST = []
WORK_GROUP_LIST = []
VERSION_1 = "1"
VERSION_2 = "0"
VERSION_3 = "0"


def reload_config():
    global MANAGER_LIST, WORK_GROUP_LIST, VERSION_1, VERSION_2, VERSION_3
    # 读取配置
    try:
        config.read(config_path)
        MANAGER_LIST = eval(config['Settings']['manager_list'])
        WORK_GROUP_LIST = eval(config['Settings']['work_group'])
        VERSION_1 = config['Settings']['version_1']
        VERSION_2 = config['Settings']['version_2']
        VERSION_3 = config['Settings']['version_3']
    except FileNotFoundError:
        logger.error("错误: 配置文件 'config.ini' 未找到！")
    except KeyError as e:
        logger.error(f"错误: 配置文件中缺少了必要的键: {e}")


__plugin_meta__ = PluginMetadata(
    name="公告",
    description="",
    usage="""
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="announcement",
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("公告", Args[Arg("command", str), Arg("arg?", int | str), Arg("arg2?", int | str)], separators=' '),
    priority=5, block=True, rule=to_me()
)


@_matcher.handle()
async def __(bot: Bot, session: Uninfo, arparma: Arparma, command: str, arg: Match[int | str], arg2: Match[str]):
    """
    command -> look | add <type> <content> | delete <id> | post
    look: 查看当前未发布的公告
    add: 添加一则公告
    delete: 删除公告
    post: 发布所有未发布公告
    """
    global VERSION_1, VERSION_2, VERSION_3, WORK_GROUP_LIST, MANAGER_LIST
    reload_config()
    group_id = session.group.id
    if group_id:
        if not group_id in WORK_GROUP_LIST:
            logger.info("公告 功能未开启", arparma.header_result, session=session)
            return await MessageUtils.build_message(["功能在本群未开启"]).send(reply_to=True)
    uid = session.user.id
    if not uid in MANAGER_LIST:
        logger.info("公告 没有权限", arparma.header_result, session=session)
        return await MessageUtils.build_message(["没有对应权限"]).send(reply_to=True)

    if command == "look":
        list1 = await Announcement.get_unpost_announcements()
        data_list = []
        for item in list1:
            data_list.append({"id": item.id,
                              "content": item.content,
                              "type": item.type})
        custom_headers = ['id', 'content', 'type']
        custom_wrap_widths = {'content': 20}

        img = create_dynamic_table_image(
            data_list,
            headers=custom_headers,
            sort_by_key='id',
            column_wrap_widths=custom_wrap_widths
        )
        if img is None:
            return await MessageUtils.build_message(["当前没有未发布的公告"]).send(reply_to=True)
        logger.info("查看公告", arparma.header_result, session=session)
        return await MessageUtils.build_message([img]).send(reply_to=True)

    if command == "add":
        if not (arg.available and arg2.available):
            logger.info("添加公告 失败", arparma.header_result, session=session)
            return await MessageUtils.build_message(["添加失败, 请检查参数"]).send(reply_to=True)
        type = str(arg.result)
        type_list = [item.value for item in announcement_type_list]
        if not type in type_list:
            logger.info("添加公告 类型错误", arparma.header_result, session=session)
            return await MessageUtils.build_message(["添加失败, 不存在的公告类型"]).send(reply_to=True)
        content = str(arg2.result)
        if content == '' or content is None:
            logger.info("添加公告 空内容", arparma.header_result, session=session)
            return await MessageUtils.build_message(["添加失败, 公告为空"]).send(reply_to=True)
        id = await Announcement.add_announcement(type, content)
        logger.info(f"添加公告成功 id={id}", arparma.header_result, session=session)
        return await MessageUtils.build_message(["添加成功"]).send(reply_to=True)

    if command == "delete":
        if not arg.available:
            logger.info("删除公告 失败", arparma.header_result, session=session)
            return await MessageUtils.build_message(["删除失败, 请检查参数"]).send(reply_to=True)
        id = str(arg.result)
        if not id.isdigit():
            logger.info("删除公告 失败", arparma.header_result, session=session)
            return await MessageUtils.build_message(["删除失败, 请检查参数"]).send(reply_to=True)
        delete = await Announcement.get_announcement(int(id))
        if delete is None:
            logger.info("删除公告 失败", arparma.header_result, session=session)
            return await MessageUtils.build_message(["删除失败, 没有这个公告"]).send(reply_to=True)
        flag = await Announcement.delete_announcement(delete.id)
        if not flag:
            logger.info("删除公告 失败", arparma.header_result, session=session)
            return await MessageUtils.build_message(["删除失败"]).send(reply_to=True)
        logger.info("删除公告 成功", arparma.header_result, session=session)
        return await MessageUtils.build_message(["删除成功"]).send(reply_to=True)

    if command == "post":
        list1 = await Announcement.get_unpost_announcements()
        if len(list1) == 0:
            return await MessageUtils.build_message(["没有要更新的公告"]).send(reply_to=True)
        list1.sort(key=lambda x: x.id)
        VERSION_2_NEW = VERSION_2
        VERSION_3_NEW = VERSION_3
        for item in list1:
            type = item.type
            if type == AnnouncementType.NEW_FEATURE.value:
                VERSION_2_NEW = str(int(VERSION_2) + 1)
            if type == AnnouncementType.BUG_FIX.value or type == AnnouncementType.IMPROVEMENT.value or type == AnnouncementType.PERFORMANCE_UPDATE.value or type == AnnouncementType.SECURITY_UPDATE.value:
                VERSION_3_NEW = str(int(VERSION_3) + 1)
        config.set('Settings', 'version_1', VERSION_1)
        config.set('Settings', 'version_2', VERSION_2_NEW)
        config.set('Settings', 'version_3', VERSION_3_NEW)
        with open(config_path, 'w') as configfile:
            config.write(configfile)
        # 构建公告文本
        version_str = f"* 版本 {VERSION_1}.{VERSION_2}.{VERSION_3} -> {VERSION_1}.{VERSION_2_NEW}.{VERSION_3_NEW}"
        description_str = ""
        for item in list1:
            description_raw = f"**  {item.type}: {item.content}\n"
            description_str += description_raw
        localtime = time.localtime(time.time())
        time_str = f"* 更新日期 {localtime.tm_year}/{localtime.tm_mon}/{localtime.tm_mday} {localtime.tm_hour}:{localtime.tm_min}:{localtime.tm_sec}"
        for g_id in WORK_GROUP_LIST:
            await MessageUtils.build_message([
                f"Bot更新公告:\n"
                f"{version_str}\n"
                f"{description_str}"
                f"{time_str}"
            ]).send(target=Target(id=g_id, self_id=bot.self_id))
        await Announcement.post_announcements(list1)
        for item in list1:
            ver = f"{VERSION_1}.{VERSION_2_NEW}.{VERSION_3_NEW}"
            await Announcement.update_announcement(id=item.id, version=ver)


def create_dynamic_table_image(
        data_list,
        headers=None,
        title=None,
        sort_by_key='id',
        column_wrap_widths=None
) -> bytes | None:
    """
    根据给定的字典列表动态生成一个表格图片。

    :param data_list: 包含字典的列表。
    :param filename: 生成图片的文件名。
    :param headers: (可选) 一个列表，定义了表头以及列的顺序。如果为 None，将自动从第一条数据中获取。
    :param title: (可选) 在表格上方显示的标题。
    :param sort_by_key: (可选) 用于对列表进行升序排序的字典键。如果为 None，则不排序。
    :param column_wrap_widths: (可选) 一个字典，用于为特定列设置文本换行宽度（字符数），例如 {'描述': 50}。
    """
    if not data_list:
        print("数据列表为空，无法生成图片。")
        return

    # 1. 确定表头
    if headers is None:
        headers = list(data_list[0].keys())

    # 2. 数据排序
    if sort_by_key and sort_by_key in headers:
        # 使用 try-except 以处理不同数据类型的排序问题
        try:
            sorted_list = sorted(data_list, key=lambda x: x.get(sort_by_key, 0))
        except TypeError:
            print(f"警告：'{sort_by_key}' 列包含无法比较的类型，将按字符串进行排序。")
            sorted_list = sorted(data_list, key=lambda x: str(x.get(sort_by_key, '')))
    else:
        sorted_list = data_list

    # 3. 表格参数设置
    try:
        font_path = script_dir + "/msyh.ttc"
        font_size = 15
        font = ImageFont.truetype(font_path, font_size)
        header_font = ImageFont.truetype(font_path, font_size + 1)
        title_font = ImageFont.truetype(font_path, font_size + 5)
    except IOError:
        print(f"字体文件 '{font_path}' 未找到，将使用默认字体。")
        font = ImageFont.load_default()
        header_font = ImageFont.load_default()
        title_font = ImageFont.load_default()

    cell_padding = 10
    line_color = (128, 128, 128)
    header_bg_color = (220, 220, 220)
    text_color = (0, 0, 0)
    default_wrap_width = 30  # 默认换行宽度（字符数）
    if column_wrap_widths is None:
        column_wrap_widths = {}

    # 4. 准备表格数据并处理文本换行
    table_data = []
    # 处理表头
    header_wrapped = [textwrap.wrap(h, width=column_wrap_widths.get(h, default_wrap_width)) for h in headers]
    table_data.append(header_wrapped)
    # 处理数据
    for item in sorted_list:
        row = [
            textwrap.wrap(str(item.get(key, '')), width=column_wrap_widths.get(key, default_wrap_width))
            for key in headers
        ]
        table_data.append(row)

    # 5. 计算尺寸
    line_height = font.getbbox("A")[3]
    header_line_height = header_font.getbbox("A")[3]

    # 计算列宽
    col_widths = [0] * len(headers)
    for row in table_data:
        for i, cell_lines in enumerate(row):
            current_font = header_font if table_data.index(row) == 0 else font
            for line in cell_lines:
                line_width = current_font.getbbox(line)[2]
                if line_width > col_widths[i]:
                    col_widths[i] = line_width
    col_widths = [w + 2 * cell_padding for w in col_widths]

    # 计算行高
    row_heights = []
    for i, row in enumerate(table_data):
        current_line_height = header_line_height if i == 0 else line_height
        max_lines_in_row = max(len(cell) for cell in row) if row else 1
        row_heights.append(max_lines_in_row * current_line_height + 2 * cell_padding)

    # 计算标题高度
    title_height = 0
    if title:
        title_height = title_font.getbbox(title)[3] + 2 * cell_padding

    # 计算图片总尺寸
    image_width = sum(col_widths)
    image_height = sum(row_heights) + title_height

    # 6. 创建图片和绘图对象
    image = Image.new('RGBA', (image_width, image_height), 'white')
    draw = ImageDraw.Draw(image)

    # 7. 绘制标题
    if title:
        title_bbox = title_font.getbbox(title)
        title_x = (image_width - title_bbox[2]) / 2
        title_y = cell_padding
        draw.text((title_x, title_y), title, font=title_font, fill=text_color)

    # 8. 绘制单元格内容
    y_offset = title_height
    for i, row in enumerate(table_data):
        x_offset = 0
        current_row_height = row_heights[i]
        is_header = (i == 0)

        for j, cell_lines in enumerate(row):
            current_col_width = col_widths[j]
            # 绘制表头背景
            if is_header:
                draw.rectangle(
                    [x_offset, y_offset, x_offset + current_col_width, y_offset + current_row_height],
                    fill=header_bg_color)

            # 绘制文本
            current_font = header_font if is_header else font
            current_line_height = header_line_height if is_header else line_height
            total_text_height = len(cell_lines) * current_line_height
            text_y_start = y_offset + (current_row_height - total_text_height) / 2

            for k, line in enumerate(cell_lines):
                line_bbox = current_font.getbbox(line)
                text_x = x_offset + (current_col_width - line_bbox[2]) / 2
                text_y = text_y_start + k * current_line_height
                draw.text((text_x, text_y), line, font=current_font, fill=text_color)
            x_offset += current_col_width
        y_offset += current_row_height

    # 9. 绘制线条
    y_offset = title_height
    # 水平线
    for h in row_heights:
        draw.line([(0, y_offset), (image_width, y_offset)], fill=line_color)
        y_offset += h
    # 最后一条水平线
    draw.line([(0, image_height - 1), (image_width, image_height - 1)], fill=line_color)
    # 垂直线
    x_offset = 0
    for w in col_widths:
        draw.line([(x_offset, title_height), (x_offset, image_height)], fill=line_color)
        x_offset += w
    draw.line([(image_width - 1, title_height), (image_width - 1, image_height)], fill=line_color)
    buf = BytesIO()
    image.save(buf, format="PNG")
    return buf.getvalue()
