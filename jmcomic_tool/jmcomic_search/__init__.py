import io
from pathlib import Path

import PIL
import aiofiles
import redis
from PIL import ImageOps
from PIL.Image import Image
from arclet.alconna.args import Arg
from jmcomic import *
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.plugin.on import on_message
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna, Match, UniMsg
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.utils.message import MessageUtils
from .data_source import *
from ..jmcomic_downloader import _ as jm_download
from ..jmcomic_info import get_jm_info

__plugin_meta__ = PluginMetadata(
    name="Jm搜索",
    description="搜索本子",
    usage="""
    指令：
        jm搜索 [搜索内容,搜索项用+连接,屏蔽项用-连接] [页码]?
        默认过滤带AI绘画的tag
        对jm搜索结果图片回复对应序号可以查看和下载对应本子
    示例：
        不带页码默认搜索第一页
            jm搜索 全彩+萝莉+...
        带页码的搜索
            jm搜索 全彩+萝莉+... 1
            jm搜索 全彩+萝莉+无修正+... 2
        带屏蔽项的搜索
            jm搜索 无修正-3D+全彩-CG集+... 1
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="jmcomic",
        limits=[
            BaseBlock(result="请稍等..."),
            PluginCdBlock(result="Jm搜索冷却中（5s）..."),
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("jm搜索", Args[Arg("search_str", str), Arg("page?", int)], separators=' '), priority=5, block=True,
    rule=to_me()
)

_index_matcher = on_message(rule=to_me(), priority=10)


def parse_search_terms(search_str: str):
    """
    解析搜索字符串，返回包含项列表和排除项列表

    参数:
        search_str: 格式为"term1[+/-]term2[+/-]term3[+/-]term4[+/-]..."的字符串

    返回:
        包含元组: (包含列表, 排除列表)
    """
    include_terms = []
    exclude_terms = []

    if not search_str:
        return include_terms, exclude_terms

    """
    先按减号分割字符串
    分隔结果为两种
    1. 单字符串, 该字符串原来被夹在两个“-”间
    2. 含“+”号字符串
    一定不会有含“-”的字符串
    对于第二种字符串, 可以确定再次分隔后的第一个字符串为“-”后的字符串
    """

    first_str = ""
    rest_str = ""
    flag = True
    for c in search_str:
        if c == '+' or c == '-':
            flag = False
        if flag:
            first_str += c
        else:
            rest_str += c

    include_terms.append(first_str)

    parts = rest_str.split('-')

    for part in parts:
        index = part.find("+")
        if index == -1:
            # 这是排除字符串
            if len(part) > 0:
                exclude_terms.append(part)
        else:
            # 再次分隔字符串
            part_subs = part.split("+")
            if len(part_subs[0]) > 0:
                exclude_terms.append(part_subs[0])
            # 剩余为包含字符串
            for sub in part_subs[1:]:
                include_terms.append(sub)

    return include_terms, exclude_terms


async def compress_image(
        image: Image.Image,
        target_size: tuple[int, int] | None = None,
        target_kb: int = 500,
        quality: int = 95
) -> Image.Image | None:
    """
    异步压缩一个 PIL.Image.Image 对象到指定的目标大小(KB)和像素尺寸。

    该函数会首先调整图片尺寸（如果提供了 target_size），然后再通过
    迭代地降低JPEG的保存质量来实现压缩。

    :param image: 需要被压缩的 PIL.Image.Image 对象。
    :param target_size: (可选) 目标像素尺寸，格式为 (width, height)。
                        如果为 None，则不改变图片尺寸。
    :param target_kb: 目标文件大小（单位：KB）。
    :param quality: 初始的压缩质量（1-95）。
    :return: 一个新的、被压缩和调整尺寸后的 PIL.Image.Image 对象，或 None。
    """

    def _compress_sync():
        """同步的压缩核心逻辑，用于在线程中执行。"""
        resized_image = image
        if target_size:
            try:
                # 使用 LANCZOS 滤镜进行高质量的缩放
                resized_image = image.resize(target_size, Image.Resampling.LANCZOS)
            except Exception as e:
                logger.error(f"调整图片尺寸时发生错误: {e}")
                return None

        # 在调整尺寸后的图片上进行压缩
        output_image = resized_image
        if output_image.mode in ('RGBA', 'P'):
            output_image = Image.new("RGB", output_image.size, (255, 255, 255))
            alpha_channel = resized_image.getchannel('A') if resized_image.mode == 'RGBA' else resized_image
            output_image.paste(resized_image, (0, 0), alpha_channel)

        final_bytes = None
        min_quality = 10
        current_quality = quality

        while current_quality >= min_quality:
            try:
                buffer = BytesIO()
                output_image.save(buffer, format="JPEG", quality=current_quality, optimize=True)

                size_kb = buffer.tell() / 1024
                final_bytes = buffer.getvalue()

                if size_kb <= target_kb:
                    return final_bytes

                current_quality -= 5
            except Exception as e:
                logger.error(f"压缩图片时发生错误: {e}")
                return None

        return final_bytes

    compressed_bytes = await asyncio.to_thread(_compress_sync)

    if compressed_bytes:
        return Image.open(BytesIO(compressed_bytes))

    return None


async def compress_image_file(image_path, target_kb=500, quality=95):
    """
    异步压缩指定路径的图片，使得压缩后文件大小不超过 target_kb KB，
    如果原文件小于目标大小则不做操作。压缩过程中保持原比例缩放，并尽可能保证图片质量。
    最后将处理后的图片覆盖原文件。
    """
    target_size = target_kb * 1024  # 目标大小（字节）

    # 异步检查原图片大小
    file_size = await asyncio.to_thread(os.path.getsize, image_path)
    if file_size <= target_size:
        logger.info("原图片已小于目标大小，无需处理。")
        return

    # 异步打开图片
    img = await asyncio.to_thread(PIL.Image.open, image_path)
    width, height = img.size

    low, high = 0.1, 1.0
    best_data = None

    for _ in range(50):  # 迭代 20 次，通常足够找到合适比例
        mid = (low + high) / 2
        new_width = int(width * mid)
        new_height = int(height * mid)
        # 异步按比例缩放图片（放到线程中执行）
        img_resized = await asyncio.to_thread(img.resize, (new_width, new_height))

        # 保存到内存中检查文件大小
        buffer = io.BytesIO()
        await asyncio.to_thread(img_resized.save, buffer, format=img.format, quality=quality, optimize=True)
        data = buffer.getvalue()
        size = len(data)

        # 如果压缩后小于目标，则记录数据，并尝试放大图片以保持较高质量
        if size <= target_size:
            best_data = data
            low = mid  # 尝试更大尺寸
        else:
            high = mid  # 需要缩小

    if best_data:
        # 异步写回原文件
        async with aiofiles.open(image_path, 'wb') as f:
            await f.write(best_data)
        logger.info("图片压缩成功，已覆盖原文件。")
    else:
        logger.info("无法将图片压缩到目标大小。")


@_matcher.handle()
async def _(bot: Bot,
            session: Uninfo,
            arparma: Arparma,
            search_str: str,
            page: Match[int]):
    # 页码有效性判断
    page_result = 1
    if page.available:
        if not str(page.result).isdigit():
            # 页码无效
            return
        page_result = page.result

    # 字符串解析
    search_params, filter_params = parse_search_terms(search_str)
    page = await JmSearchPageManager(search_params=search_params, filter_params=filter_params,
                                     page=page_result).async_init()

    if len(page.search_page_detail.get_albums()) == 0:
        # 没有搜索结果
        await (MessageUtils.build_message([f"没有搜索结果"])
               .send(reply_to=True))
        return

    if len(page.search_page_detail.get_albums()) == 1:
        album_id = page.search_page_detail.get_albums()[0].get_album_id()
        # 只有一个搜索结果则返回该结果的jm信息
        try:
            return await get_jm_info(bot, session, album_id)
        except Exception as e:
            # 无法直接发送封面则发送搜索结果图片
            pass

    img = await page.create_page_img()
    if img is None:
        await (MessageUtils.build_message([f"搜索结果生成失败"])
               .send(reply_to=True))
        return

    uid = session.user.id
    compress_img = await compress_image(img, target_size=(1360, 2001), target_kb=4096, quality=95)
    compress_img.save((Path() / f"{BASE_PATH}/{uid}.jpg").absolute())

    # 发送图片
    try:
        msg = await (MessageUtils.build_message([Path() / f"{BASE_PATH}/{uid}.jpg", f"\n[回复'序号'查看和下载对应本子,回复'列表'获取搜索结果jm列表]"])
                     .send(reply_to=True))
        msg_id = msg.msg_ids[0].get('message_id')
    except Exception as e:
        logger.error("发送jm搜索结果失败, 尝试发送反转图片", session=session, e=e)

        # 如果原图发送失败，则尝试发送反转后的图片
        try:
            # 调用函数来反转并保存图片
            reverse_img_path = await reverse_and_save_image(compress_img, Path() / f"{BASE_PATH}/{uid}.jpg")

            # 发送反转后的图片
            msg = await (MessageUtils.build_message([reverse_img_path, f"\n[回复'序号'查看和下载对应本子,回复'列表'获取搜索结果jm列表]"])
                         .send(reply_to=True))
            msg_id = msg.msg_ids[0].get('message_id')
            logger.info("JM搜索结果反转图片发送成功。")
        except Exception as e_reverse:
            logger.error("发送反转后的图片也失败了", session=session, e=e_reverse)

    # 缓存搜索结果
    try:
        cache = []
        for album in page.search_page_detail.get_albums():
            album_id = album.get_album_id()
            cache.append(album_id)
        connect = redis.Redis(host='localhost', port=6379, decode_responses=True, password='xxx')
        connect.rpush(msg_id, *cache)
        connect.expire(msg_id, 24 * 60 * 60)
    except Exception as e:
        print(e)
        logger.info(f"jm搜索缓存失败", arparma.header_result, session=session)
    logger.info(f"jm搜索 {search_str}", arparma.header_result, session=session)


@_index_matcher.handle()
async def __(bot: Bot, session: Uninfo, event: MessageEvent, message: UniMsg):
    index = message.extract_plain_text()
    if not str(index).isdigit():
        if not str(index) == "列表":
            return

    msg = await bot.get_msg(message_id=event.message_id)
    # 获取消息内容
    match = re.search(r'\[CQ:reply,id=(\d+)\]', msg.get('raw_message'))
    reply_msg = await bot.get_msg(message_id=match.group(1))
    message_id = reply_msg.get('message_id')
    match2 = re.search(r'\[CQ:reply,id=(\d+)\]', reply_msg.get('raw_message'))
    reply_msg2 = await bot.get_msg(message_id=match2.group(1))
    text_content = reply_msg2.get('raw_message')
    # 判断是否需要回复
    match = re.search(r'jm搜索', text_content)
    if not match:
        return
    connect = redis.Redis(host='localhost', port=6379, decode_responses=True, password='xxx')
    if not connect.exists(message_id):
        return await (MessageUtils.build_message([f"缓存过期, 请重新搜索"])
                      .send(reply_to=True))
    list = connect.lrange(message_id, 0, -1)
    if str(index) == "列表":
        msg = ""
        for i, a_id in enumerate(list, start=1):
            msg = msg + f"{i}、JM[{a_id}]\n"
        await MessageUtils.build_message([msg]).send(reply_to=True)
    else:
        index = int(index)
        a_id = list[index - 1]
        try:
            await get_jm_info(bot, session, a_id)
        except Exception as e:
            logger.error("发送jm信息失败", session=session, e=e)
        try:
            return await jm_download(bot, session, None, a_id)
        except Exception as e:
            logger.error("下载失败", session=session, e=e)
            return


async def reverse_and_save_image(img: Image.Image, original_path: Path) -> Path:
    """
    垂直反转图片，并以'-reverse'后缀保存。

    Args:
        img (Image.Image): 原始的Pillow图片对象。
        original_path (Path): 原始图片的保存路径。

    Returns:
        Path: 反转后图片的保存路径。
    """
    try:
        # 垂直（上下）翻转图片
        reversed_img = ImageOps.flip(img)

        # 构建新的文件路径，例如 "123.jpg" -> "123-reverse.jpg"
        reverse_stem = f"{original_path.stem}-reverse"
        reverse_path = original_path.with_stem(reverse_stem)

        # 保存反转后的图片
        reversed_img.save(reverse_path.absolute())
        logger.info(f"图片已反转并保存至: {reverse_path.absolute()}")
        return reverse_path
    except Exception as e:
        logger.error(f"反转并保存图片时出错: {e}")
        raise
