import asyncio
import concurrent
import concurrent.futures
import configparser
import io
import math
import os
import re
import time
import zipfile
from pathlib import Path

import aiofiles
import html2text
import img2pdf
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
from arclet.alconna import Arg
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna, Match
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

BASE_PATH = "resources/pivix/image"
HTMLTOTEXT = html2text.HTML2Text()
HTMLTOTEXT.body_width = 0

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.ini')
config = configparser.ConfigParser()
# --- 配置 ---
API_TOKEN = "xxx"
SERVER_IP = "xxx"
SERVER_PORT = 500
HEADER_REFERER = "https://www.pixiv.net/"
HEADER_USERAGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.0.0 Safari/537.36"
COOKIE_PHPSESSID = "xxx"
PROXY_SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
MANAGER_LIST: list[str] = []
FILTER_GROUP_LIST: list[str] = []
WORK_GROUP_LIST: list[str] = []


def reload_config():
    global API_TOKEN, SERVER_IP, SERVER_PORT, HEADER_REFERER, HEADER_USERAGENT, COOKIE_PHPSESSID, PROXY_SERVER_URL, MANAGER_LIST, FILTER_GROUP_LIST, WORK_GROUP_LIST
    # 读取配置
    try:
        config.read(config_path)
        API_TOKEN = config['Authentication']['api_token']
        SERVER_IP = config['ProxySettings']['server_ip']
        SERVER_PORT = config['ProxySettings']['server_port']
        HEADER_REFERER = config['Authentication']['api_header_Referer']
        HEADER_USERAGENT = config['Authentication']['api_header_UserAgent']
        COOKIE_PHPSESSID = config['Authentication']['api_cookie_PHPSESSID']
        PROXY_SERVER_URL = f"http://{SERVER_IP}:{SERVER_PORT}"
        MANAGER_LIST = eval(config['UserSettings']['manager_list'])
        FILTER_GROUP_LIST = eval(config['UserSettings']['filter_group'])
        WORK_GROUP_LIST = eval(config['UserSettings']['work_group'])
    except FileNotFoundError:
        logger.error("错误: 配置文件 'config.ini' 未找到！")
    except KeyError as e:
        logger.error(f"错误: 配置文件中缺少了必要的键: {e}")


reload_config()

__plugin_meta__ = PluginMetadata(
    name="P站解析",
    description="使用pid获取图片, 使用pid获取图片信息, 使用画师id获取画师信息",
    usage="""
    指令：
        1. 根据pid获取图片, 图片大小可选参数S、M、L, 默认M, 序号可选参数, 默认1, 使用all获取所有插画
        pid [插画id]<图片大小> <序号>
        2. 解析pid对应作品信息, 返回包含图片直链, 使用可选参数序号控制图片直链指向作品对应顺序的插画
        pinfo [插画id] <序号>
        3. 获取画师简要信息, 画师主页, 画师作品数量
        puser [画师id]
        4. 获取画师详细信息, 数量可选参数表示查看对应画师最新对应数量的作品, 使用all表示获取所有作品, 默认50, 返回消息类型可选参数html、img, 默认html
        puser-d [画师id] <数量> <返回消息类型>
    示例：
        1.
         默认获取第一张插画, 默认小图
          pid 90457556
         默认获取第一张插画, 原图, 最慢
          pid 90457556L
         默认获取第一张插画, 小图
          pid 90457556M
         默认获取第一张插画, 略缩图, 最快
          pid 90457556S
         获取第二张插画, 默认小图
          pid 90457556 2
         获取第二张插画, 大图
          pid 90457556L 2
         获取所有插画, 图片大小参数仍可用
          pid 90457556 all
          pid 90457556L all
         获取插画并以pdf文件发送, 图片大小参数仍可用
          pid 90457556 pdf
          pid 90457556L 2 pdf
          pid 90457556 all pdf
          pid 90457556L all pdf
        2.
         解析pid=90457556的作品信息, 包含第一张插画的图片直链
          pinfo 90457556
         解析pid=90457556的作品信息, 包含第二张插画的图片直链
          pinfo 90457556 2
        3.
         获取画师简要信息, 画师主页, 画师作品数量, 前6个作品
          puser 16985944
        4.
         获取id=16985944的画师信息, 第一页，每页50个
          puser-d 16985944
         获取id=16985944的画师信息, 第二页
          puser-d 16985944 2
         获取id=16985944的画师信息, 返回html文件，包括所有作品，内置分页
          puser-d 16985944 html
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="一些工具",
        limits=[
            BaseBlock(result="当前有图片正在下载，请稍等..."),
            PluginCdBlock(result="P站PID解析冷却中（5s）..."),
        ],
    ).to_dict(),
)

_info_matcher1 = on_alconna(
    Alconna("pid", Args[Arg("illust_id", str), Arg("index?", str), Arg("is_pdf?", str)], separators=' '), priority=5,
    block=True
)

_info_matcher2 = on_alconna(
    Alconna("pinfo", Args[Arg("illust_id", str), Arg("index?", str)], separators=' '), priority=5, block=True
)

_info_matcher3 = on_alconna(
    Alconna("puser", Args["user_id", str], separators=' '), priority=5, block=True
)

_info_matcher4 = on_alconna(
    Alconna("puser-d", Args[Arg("user_id", str), Arg("num?", int)], separators=' '), priority=5,
    block=True
)

_update_matcher = on_alconna(
    Alconna("pid更新凭证", Args["token", str], separators=' '), priority=5, block=True
)


def call_proxy(method: str, target_url: str, query_params: dict | None = None, json_body: dict | None = None,
               custom_headers: dict | None = None, cookies: dict | None = None,
               return_format: str = 'json'):
    """
    通过一个安全的代理服务器向指定的目标 URL 发送 HTTP 请求。

    此函数封装了与代理服务器的所有交互细节，包括构造请求、
    自动添加认证 Token，以及处理响应和错误。

    Args:
        method (str):
            要使用的 HTTP 请求方法。
            格式: 一个字符串，不区分大小写，但通常使用大写。
            示例: 'GET', 'POST', 'PUT', 'DELETE'

        target_url (str):
            请求最终要到达的目标服务的完整 URL。
            格式: 一个包含协议 (http/https) 的标准 URL 字符串。
            示例: 'https://api.github.com/users/google'

        query_params (dict, optional):
            要附加到 target_url 末尾的查询参数。默认为 None。
            格式: 一个键和值都为字符串的字典。
            示例: {'page': '2', 'per_page': '50'}
                 会被转换为 "...?page=2&per_page=50"

        json_body (dict, optional):
            要作为请求体发送的 JSON 数据，通常用于 'POST' 或 'PUT' 请求。默认为 None。
            格式: 一个可以被序列化为 JSON 的 Python 字典。
            示例: {'username': 'test', 'permissions': ['read', 'write']}

        custom_headers (dict, optional):
            需要发送给 *目标服务器* 的自定义 HTTP 请求头。默认为 None。
            注意：本函数会自动处理发往代理服务器的 'Authorization' 头。
            格式: 一个键和值都为字符串的字典。
            示例: {'X-Request-ID': 'some-unique-value', 'Accept-Language': 'en-US'}

        cookies (dict, optional):
            需要发送给 *目标服务器* 的 Cookies。默认为 None。
            格式: 一个键和值都为字符串的字典。
            示例: {'session_id': 'abc-123-xyz', 'user_theme': 'dark'}
        return_format (str, optional):
            期望的返回格式。默认为 'json'。
            可选项: 'json' 或 'binary'。
            - 'json': 函数返回一个 Python 字典。
            - 'binary': 函数返回原始的字节数据 (bytes)。

    Returns:
        dict | None:
            - 如果 return_format='json', 成功时返回字典，失败时返回 None。
            - 如果 return_format='binary', 成功时返回字节串，失败时返回 None。
    """
    proxy_params = {'url': target_url}
    if query_params:
        proxy_params.update(query_params)

    if return_format.lower() == 'binary':
        proxy_params['return_as'] = 'binary'

    headers_to_send = {'Authorization': API_TOKEN}
    if custom_headers:
        headers_to_send.update(custom_headers)

    logger.info(f"--- 准备通过代理发送 {method} 请求 ---")
    logger.info(f"目标: {target_url}")

    start_time = time.perf_counter()  # <--- 新增：在请求开始前记录精确时间

    try:
        response = requests.request(
            method=method.upper(),
            url=PROXY_SERVER_URL,
            params=proxy_params,
            json=json_body,
            headers=headers_to_send,
            cookies=cookies,
            timeout=60
        )
        response.raise_for_status()

        end_time = time.perf_counter()
        duration = end_time - start_time
        logger.info(f"  └──> 响应成功，耗时: {duration:.3f} 秒")

        # 根据期望的格式返回不同的内容
        if return_format.lower() == 'binary':
            return response.content  # 返回原始字节
        else:
            return response.json()  # 返回解析后的 JSON

    except requests.exceptions.HTTPError as e:
        logger.error(f"[!] HTTP 错误: {e.response.status_code} {e.response.reason}")
        if e.response.status_code in [401, 403]:
            logger.error("[!] 认证失败 (无效或缺失的 Token)。服务器未返回任何数据。")
        else:
            logger.error(f"[!] 服务器响应: {e.response.text}")
        return None
    except requests.exceptions.RequestException as e:
        logger.error(f"[!] 请求发生严重错误: {e}")
        return None


@_info_matcher1.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, illust_id: str, index: Match[str], is_pdf: Match[str]):
    if session.group:
        if not validate_permission(session):
            return
    reload_config()
    # 取得图片大小标识
    flag = illust_id[-1]
    if flag == 'S' or flag == 'M' or flag == 'L':
        illust_id = illust_id[:len(illust_id) - 1]
    else:
        if str(flag).isdigit():
            flag = 'M'

    # 图片元数据
    metadata_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
    # 动图元数据
    ugoira_meta_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}/ugoira_meta"
    get_params = {'lang': 'zh'}
    get_headers = {
        'User-Agent': HEADER_USERAGENT,
        'Referer': HEADER_REFERER
    }
    get_cookies = {
        'PHPSESSID': COOKIE_PHPSESSID
    }

    metadata_response = call_proxy(
        method="GET",
        target_url=metadata_api_url,
        query_params=get_params,
        custom_headers=get_headers,
        cookies=get_cookies,
        return_format='json'
    )

    if not metadata_response:
        await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
        logger.info("pid解析失败")
    # 作者ID
    author_id = None
    # 作者名
    author_name = None
    # 图片url
    image_url: str = ""
    # 标题
    tile = None
    # 页数
    pages = None
    # 页码
    page_no = None
    # 图片代理链接
    image_url_proxy = ""

    # 解析图片信息
    try:
        # 2025/10/21 检查图片是否为动图
        match = re.search(r'ugoira', metadata_response['body']['body']['urls']['original'])
        if match:
            # 该插画为动图
            raise UgoiraException
        author_id = metadata_response['body']['body']['userId']
        author_name = metadata_response['body']['body']['userName']
        image_url = metadata_response['body']['body']['urls']['regular']
        if flag == 'S':
            image_url = metadata_response['body']['body']['urls']['small']
        if flag == 'M':
            image_url = metadata_response['body']['body']['urls']['regular']
        if flag == 'L':
            image_url = metadata_response['body']['body']['urls']['original']
        tile = metadata_response['body']['body']['illustTitle']
        pages = metadata_response['body']['body']['pageCount']
        page_no = "1"
        if index.available:
            if index.result:
                page_no = index.result
        # 图片反代链接
        image_url_proxy = image_url.replace("i.pximg.net", "i.pixiv.cat")
    except UgoiraException:
        # 处理动图
        ugoira_metadata_response = call_proxy(
            method="GET",
            target_url=ugoira_meta_api_url,
            query_params=get_params,
            custom_headers=get_headers,
            cookies=get_cookies,
            return_format='json'
        )

        if not ugoira_metadata_response:
            await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
            logger.info("pid解析失败")
        try:
            # 压缩包代理链接
            original_src = ugoira_metadata_response['body']['body']['originalSrc']
            # 动图参数
            frames = ugoira_metadata_response['body']['body']['frames']
            # 输出路径
            output_zip_filename = f"{BASE_PATH}/{illust_id}_ugoira_original.zip"
            output_gif_filename = f"{BASE_PATH}/{illust_id}_ugoira.gif"
            package_zip_filename = f"{BASE_PATH}/{illust_id}_ugoira.zip"
            # 压缩包反代链接
            src_url_proxy = original_src.replace("i.pximg.net", "i.pixiv.cat");
            zip_path = Path(output_zip_filename)
            gif_path = Path(output_gif_filename)
            package_path = Path(package_zip_filename)

            if not gif_path.exists():
                src_bytes = call_proxy(
                    method="GET",
                    target_url=src_url_proxy,
                    return_format='binary'
                )
                if not src_bytes:
                    logger.warning(f"下载PID {illust_id} 的动图资源文件失败")
                    raise IOError("下载动图资源失败")
                try:
                    with open(output_zip_filename, "wb") as f:
                        f.write(src_bytes)
                    logger.info(f"pid动图ZIP保存成功: {illust_id}")
                except IOError as e:
                    logger.error(f"pid动图ZIP保存失败, {e}")
                    return await MessageUtils.build_message(["图片下载失败"]).send(reply_to=True)

            # 加载动图资源文件并转换为GIF
            conversion_success = await convert_ugoira_zip_to_gif(
                str(zip_path),
                frames,
                str(gif_path)
            )

            if not conversion_success:
                return await MessageUtils.build_message(["动图处理失败"]).send(reply_to=True)
            package = await package_file_to_zip(source_file_path=str(gif_path), zip_file_path=str(package_path))
            if not package:
                # 打包失败
                return await MessageUtils.build_message(["动图打包失败"]).send(reply_to=True)
            try:
                # 发送gif文件
                if session.group:
                    await bot.upload_group_file(
                        group_id=session.group.id,
                        file=str(package_path.absolute()),
                        name=package_path.name,
                    )
                else:
                    await bot.upload_private_file(
                        user_id=session.user.id,
                        file=str(package_path.absolute()),
                        name=package_path.name,
                    )
                logger.info(f"pid解析 {illust_id} [PDF发送成功]", arparma.header_result, session=session)
            except Exception as pdf_e:
                # PDF发送失败，就只回复一条错误信息
                logger.error(f"发送gif失败: {pdf_e}")
                await MessageUtils.build_message(["动图发送失败"]).send(reply_to=True)

            # 删除临时ZIP文件
            try:
                zip_path.unlink()
                logger.info(f"已删除临时动图ZIP文件: {zip_path.name}")
            except OSError as e:
                logger.error(f"删除临时ZIP文件失败: {e}")
        except Exception:
            await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
            logger.info("pid解析失败")
        # 直接结束流程
        return
    except Exception:
        await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
        logger.info("pid解析失败")

    # 构建页码表
    page_nos = []
    if page_no != "all" and page_no != "pdf" and page_no.isdigit():
        # 页码参数有效
        page_nos.append(page_no)
    elif page_no == "pdf":
        # 没有页码参数有pdf参数
        page_nos.append("1")
    elif page_no == "all":
        # 页码参数为all
        page_nos = [str(x) for x in range(1, int(pages) + 1)]
    else:
        # 无效参数默认返回第一张图片
        page_no = "1"
        page_nos.append("1")

    # 图片列表
    downloaded_files = []
    # 消息列表
    msg_elements = []

    for current_page in page_nos:
        suffix = ""
        if pages > 1:
            suffix = f"-{current_page}"
        output_filename = f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
        path = Path(output_filename)

        if not path.exists():
            image_url_proxy_2 = image_url_proxy.replace("_p0", f"_p{int(current_page) - 1}")
            image_bytes = call_proxy(
                method="GET",
                target_url=image_url_proxy_2,
                return_format='binary'
            )
            if not image_bytes:
                logger.warning(f"下载PID {illust_id} 的第 {current_page} 页失败")
                continue
            try:
                with open(output_filename, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"pid图片保存成功: {illust_id} -p{current_page}")
            except IOError as e:
                logger.error(f"pid图片保存失败, {e}")
                continue

        absolute_path = path.absolute()
        # 2025/10/21 QQ聊天图片大小限制12MB 缩小到10MB
        await compress_image(image_path=absolute_path, target_kb=10240, quality=100)
        downloaded_files.append(str(absolute_path))
        msg_elements.append(path)

    if not downloaded_files:
        logger.error(f"pid获取图片失败: {illust_id}，所有图片都下载失败。")
        await MessageUtils.build_message(["图片下载失败，无法发送。"]).send(reply_to=True)
        return

    # 添加描述文本
    msg_elements.append("\n")
    msg_elements.append(f"{tile}\n* 作者: {author_name}/{author_id}\n共 {pages} 页")

    # 尝试发送图片, 如果失败则转为PDF
    try:
        # 处理需要直接发送pdf的情况
        if page_no == "pdf":
            raise Exception
        if is_pdf.available:
            if str(is_pdf.result) == "pdf":
                raise Exception

        logger.info("尝试直接发送图片...")
        await MessageUtils.build_message(msg_elements).send(reply_to=False)
        logger.info(f"pid解析 {illust_id} [图片发送成功]", arparma.header_result, session=session)
    except Exception as e:
        logger.warning(f"直接发送图片失败: {e}. 尝试转为PDF发送...")

        # 构建插件信息图片
        info_text = "本插件及其相关已在GitHub开源, 详见:\nhttps://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev"
        info_page_bytes = create_text_image(info_text)
        if info_page_bytes:
            downloaded_files.append(info_page_bytes)

        try:
            # 定义PDF文件名
            pdf_name_suffix = f"-{page_no}" if len(page_nos) == 1 else "-all"
            pdf_file_path = Path(f"{BASE_PATH}/{illust_id}{flag}{pdf_name_suffix}.pdf")
            # 先判断文件是否存在
            if not pdf_file_path.exists():
                # 使用已有的 downloaded_files 列表创建PDF
                with open(pdf_file_path, "wb") as f:
                    f.write(img2pdf.convert(downloaded_files))
                logger.info(f"PDF创建成功: {pdf_file_path}")

            # 发送PDF文件
            if session.group:
                await bot.upload_group_file(
                    group_id=session.group.id,
                    file=str(pdf_file_path.absolute()),
                    name=pdf_file_path.name,
                )
            else:
                await bot.upload_private_file(
                    user_id=session.user.id,
                    file=str(pdf_file_path.absolute()),
                    name=pdf_file_path.name,
                )
            logger.info(f"pid解析 {illust_id} [PDF发送成功]", arparma.header_result, session=session)

        except Exception as pdf_e:
            # PDF发送失败，就只回复一条错误信息
            logger.error(f"发送PDF也失败了: {pdf_e}")
            await MessageUtils.build_message(["图片发送失败，尝试转为PDF文件发送也失败了。"]).send(reply_to=True)


@_info_matcher2.handle()
async def __(bot: Bot, session: Uninfo, arparma: Arparma, illust_id: str, index: Match[str]):
    if session.group:
        if not validate_permission(session):
            return
    reload_config()
    flag = 'S'
    metadata_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
    get_params = {'lang': 'zh'}
    get_headers = {
        'User-Agent': HEADER_USERAGENT,
        'Referer': HEADER_REFERER
    }
    get_cookies = {
        'PHPSESSID': COOKIE_PHPSESSID
    }

    metadata_response = call_proxy(
        method="GET",
        target_url=metadata_api_url,
        query_params=get_params,
        custom_headers=get_headers,
        cookies=get_cookies,
        return_format='json'  # 明确指定需要 JSON
    )

    # 作者ID
    author_id = None
    # 作者名
    author_name = None
    # 图片url
    image_url_small: str = ""
    image_url_original: str = ""
    # 标题
    tile = None
    # 插画备注
    illust_comment = None
    # 标签
    tags = None
    # 页数
    pages = None
    # 页码
    page_no = None
    if metadata_response:
        # 解析图片信息
        try:
            author_id = metadata_response['body']['body']['userId']
            author_name = metadata_response['body']['body']['userName']
            image_url_small = metadata_response['body']['body']['urls']['small']
            image_url_original = metadata_response['body']['body']['urls']['original']
            tile = metadata_response['body']['body']['illustTitle']
            illust_comment = metadata_response['body']['body']['illustComment']
            tags = get_tags_str(metadata_response['body']['body']['tags']['tags'])
            pages = metadata_response['body']['body']['pageCount']
            page_no = "1"
            if index.available:
                if not index.result:
                    # 页码无效
                    return
                page_no = index.result

            if page_no != "1":
                image_url_small = image_url_small.replace("_p0", f"_p{int(page_no) - 1}")
                image_url_original = image_url_original.replace("_p0", f"_p{int(page_no) - 1}")

            image_url_small_proxy = image_url_small.replace("i.pximg.net", "i.pixiv.cat")
            image_url_original_proxy_1 = image_url_original.replace("i.pximg.net", "i.yuki.sh")
            image_url_original_proxy_2 = image_url_original.replace("i.pximg.net", "i.pixiv.re")
            image_url_original_proxy_3 = image_url_original.replace("i.pximg.net", "i.pixiv.nl")

        except Exception:
            await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
            logger.info("pid解析失败")

    try:
        suffix = ""
        if pages > 1:
            suffix = f"-{page_no}"
        output_filename = f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
        path = Path() / f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
        if path.exists():
            logger.info(f"  └──> 图片已存在")
            try:
                # 发送图片
                await (MessageUtils.build_message([Path() / f"{BASE_PATH}/{illust_id}{suffix}{flag}.png",
                                                   f"作品信息:\n",
                                                   f"* 标题: {tile}\n",
                                                   f"* 简介: {HTMLTOTEXT.handle(illust_comment)}\n",
                                                   f"* 标签: [{tags}]\n",
                                                   f"* 作者: {author_name}/{author_id}\n",
                                                   f"共 {pages} 幅作品\n",
                                                   f"当前为第 {page_no} 幅作品\n",
                                                   f"\n",
                                                   f"查看原图:\n",
                                                   f"* 备用链接1: {image_url_original_proxy_1}\n",
                                                   f"* 备用链接2: {image_url_original_proxy_2}\n",
                                                   f"* 备用链接3: {image_url_original_proxy_3}\n",
                                                   f"\n",
                                                   f"来源:\n",
                                                   f"* 作者: https://www.pixiv.net/users/{author_id}\n",
                                                   f"* 作品: https://www.pixiv.net/artworks/{illust_id}\n",
                                                   f"* \n",
                                                   f"本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev", ])
                       .send(reply_to=True))
                logger.info(f"pid解析 {illust_id}", arparma.header_result, session=session)
                return
            except Exception as e:
                raise Exception(e)

        image_bytes = call_proxy(
            method="GET",
            target_url=image_url_small_proxy,
            return_format='binary'
        )
        if image_bytes:
            # 将获取到的二进制数据保存为文件
            try:
                with open(output_filename, "wb") as f:
                    f.write(image_bytes)
                logger.info(f"pid图片保存成功: {illust_id}")
                # 发送图片
                await (MessageUtils.build_message([Path() / f"{BASE_PATH}/{illust_id}{suffix}{flag}.png",
                                                   f"作品信息:\n",
                                                   f"* 标题: {tile}\n",
                                                   f"* 简介: {HTMLTOTEXT.handle(illust_comment)}\n",
                                                   f"* 标签: [{tags}]\n",
                                                   f"* 作者: {author_name}/{author_id}\n",
                                                   f"共 {pages} 幅作品\n",
                                                   f"当前为第 {page_no} 幅作品\n",
                                                   f"\n",
                                                   f"查看原图:\n",
                                                   f"* 备用链接1: {image_url_original_proxy_1}\n",
                                                   f"* 备用链接2: {image_url_original_proxy_2}\n",
                                                   f"* 备用链接3: {image_url_original_proxy_3}\n",
                                                   f"\n",
                                                   f"来源:\n",
                                                   f"* 作者: https://www.pixiv.net/users/{author_id}\n",
                                                   f"* 作品: https://www.pixiv.net/artworks/{illust_id}\n",
                                                   f"* \n",
                                                   f"本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev", ])
                       .send(reply_to=True))
                logger.info(f"pid解析 {illust_id}", arparma.header_result, session=session)
            except IOError as e:
                logger.error(f"pid图片保存失败, {e}")
                raise Exception()
        else:
            raise Exception()
    except Exception:
        logger.error(f"pid获取图片失败: {illust_id}")


@_info_matcher3.handle()
async def ___(bot: Bot, session: Uninfo, arparma: Arparma, user_id: str):
    if session.group:
        if not validate_permission(session):
            return
    pass


@_info_matcher4.handle()
async def ____(bot: Bot, session: Uninfo, arparma: Arparma, user_id: str, num: Match[int]):
    if session.group:
        if not validate_permission(session):
            return
    # 页码
    number = 1
    is_html = False
    if num.available:
        if str(num.result).isdigit():
            # 数量有效
            number = num.result
        else:
            # 不是有效数字, 验证是否信息类型
            if str(num.result) == "html":
                is_html = True

    # 画师作品元数据
    metadata_work_url = f"https://www.pixiv.net/ajax/user/{user_id}/works/latest"
    # 画师信息元数据
    metadata_user_url = f"https://www.pixiv.net/ajax/user/{user_id}"

    get_params1 = {'lang': 'zh'}
    get_params2 = {'lang': 'zh',
                   'full': '1'}
    get_headers = {
        'User-Agent': HEADER_USERAGENT,
        'Referer': HEADER_REFERER
    }
    get_cookies = {
        'PHPSESSID': COOKIE_PHPSESSID
    }

    metadata_work_response = call_proxy(
        method="GET",
        target_url=metadata_work_url,
        query_params=get_params1,
        custom_headers=get_headers,
        cookies=get_cookies,
        return_format='json'
    )
    metadata_user_response = call_proxy(
        method="GET",
        target_url=metadata_user_url,
        query_params=get_params2,
        custom_headers=get_headers,
        cookies=get_cookies,
        return_format='json'
    )
    if not metadata_work_response or not metadata_user_response:
        await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
        logger.info("pid解析失败")

    # 作品列表
    author_name = ""
    works = []
    # 头像
    avatar = ""
    avatar_url = ""
    avatar_url_proxy = ""
    # 背景图像
    background = ""
    background_url = ""
    background_url_proxy = ""

    author_name = metadata_user_response['body']['body']['name']
    illusts = metadata_work_response['body']['body']['illusts']
    avatar_url = metadata_user_response['body']['body']['imageBig']
    avatar_url_proxy = avatar_url.replace("i.pximg.net", "i.pixiv.cat")
    try:
        background_url = metadata_user_response['body']['body']['background']['url']
        background_url_proxy = background_url.replace("i.pximg.net", "i.pixiv.cat")
    except Exception:
        background_url = ""
        background_url_proxy = ""

    work_id_strings = illusts.keys()
    work_id_integers = [int(id_str) for id_str in work_id_strings]
    work_id_integers.sort(reverse=True)
    sorted_work_ids = work_id_integers
    # 定义分页参数
    page_size = 50
    current_page = number
    total_page = int(math.ceil(len(sorted_work_ids) / page_size))
    start_index = (current_page - 1) * page_size
    end_index = current_page * page_size
    current_page_ids = sorted_work_ids[start_index:end_index]
    if is_html:
        # TODO 生成html
        return

    for illust_id in current_page_ids:
        output_filename = f"{BASE_PATH}/{illust_id}S.png"
        path = Path(output_filename)
        absolute_path = path.absolute()
        works.append(absolute_path)

    # 依次下载
    def download_worker(illust_id: str) -> dict:
        """
        同步下载单个图片的函数。
        返回一个字典来表示结果，而不是在线程中执行 await 操作。
        """
        output_filename = f"{BASE_PATH}/{illust_id}S.png"
        path = Path(output_filename)

        if path.exists():
            return {'status': 'skipped', 'id': illust_id}

        try:
            # 获取图片元数据
            metadata_api_url = f"https://www.pixiv.net/ajax/illust/{illust_id}"
            metadata_response = call_proxy(
                method="GET",
                target_url=metadata_api_url,
                query_params=get_params1,
                custom_headers=get_headers,
                cookies=get_cookies,
                return_format='json'
            )
            if not metadata_response:
                return {'status': 'error', 'id': illust_id, 'reason': '元数据请求失败'}

            # 解析图片URL
            image_url = metadata_response['body']['body']['urls']['small']
            image_url_proxy = image_url.replace("i.pximg.net", "i.pixiv.cat")

            # 下载图片
            image_bytes = call_proxy(
                method="GET",
                target_url=image_url_proxy,
                return_format='binary'
            )
            if not image_bytes:
                return {'status': 'error', 'id': illust_id, 'reason': '图片下载失败'}

            # 保存图片
            with open(output_filename, "wb") as f:
                f.write(image_bytes)

            logger.info(f"成功下载: {illust_id}")
            return {'status': 'success', 'id': illust_id}

        except Exception as e:
            logger.error(f"处理 {illust_id} 时发生意外错误: {e}")
            return {'status': 'error', 'id': illust_id, 'reason': f'意外错误: {e}'}

    loop = asyncio.get_running_loop()
    failed_tasks = []

    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
        futures = [
            loop.run_in_executor(executor, download_worker, illust_id)
            for illust_id in current_page_ids
        ]
        results = await asyncio.gather(*futures)

    for result in results:
        if result and result['status'] == 'error':
            failed_tasks.append(result['id'])
            logger.info(f"pid处理失败: {result['id']}, 原因: {result['reason']}")

    if failed_tasks:
        failed_ids_str = ", ".join(failed_tasks)
        await MessageUtils.build_message([f"处理完成，但以下PID失败了: {failed_ids_str}"]).send(reply_to=True)

    # 下载头像
    output_filename = f"{BASE_PATH}/{user_id}-avatar.png"
    path = Path(output_filename)

    if not path.exists():
        image_bytes = call_proxy(
            method="GET",
            target_url=avatar_url_proxy,
            return_format='binary'
        )
        if image_bytes:
            try:
                with open(output_filename, "wb") as f:
                    f.write(image_bytes)
                    avatar = path.absolute()
            except IOError as e:
                logger.error(f"图片保存失败, {e}")
    else:
        avatar = path.absolute()
    # 下载背景
    output_filename = f"{BASE_PATH}/{user_id}-background.png"
    path = Path(output_filename)
    if background_url_proxy != "":
        if not path.exists():
            image_bytes = call_proxy(
                method="GET",
                target_url=background_url_proxy,
                return_format='binary'
            )
            if image_bytes:
                try:
                    with open(output_filename, "wb") as f:
                        f.write(image_bytes)
                        background = path.absolute()
                except IOError as e:
                    logger.error(f"图片保存失败, {e}")
        else:
            background = path.absolute()
    else:
        background = None

    result = await create_user_display_image(background,
                                             avatar,
                                             works,
                                             author_name,
                                             current_page,
                                             total_page,
                                             2000)
    result.save((Path() / f"{BASE_PATH}/{session.user.id}-userd.png").absolute())
    await compress_image(image_path=(Path() / f"{BASE_PATH}/{session.user.id}-userd.png").absolute(), target_kb=10240,
                         quality=100)
    await MessageUtils.build_message([Path() / f"{BASE_PATH}/{session.user.id}-userd.png"]).send(reply_to=True)


@_update_matcher.handle()
async def _____(bot: Bot, session: Uninfo, arparma: Arparma, token: str, event: MessageEvent):
    if session.group:
        if not validate_permission(session):
            return
    uid = session.user.id
    if uid in MANAGER_LIST:
        try:
            config.set('Authentication', 'api_cookie_PHPSESSID', token)
            with open(config_path, 'w') as configfile:
                config.write(configfile)
        except Exception:
            await MessageUtils.build_message(["狗修金~, 更新凭证失败了呢"]).send(reply_to=True)
            return
        await MessageUtils.build_message(["狗修金~, 更新凭证成功啦！"]).send(reply_to=True)
    else:
        await MessageUtils.build_message(["没有对应权限"]).send(reply_to=True)


def get_tags_str(tag_list: list) -> str:
    tag_str = ""
    for tag in tag_list:
        origin_tag = tag['tag']
        translation_tag = ""
        try:
            translation_tag = tag['translation']['en']
        except Exception:
            pass
        dot = ", "
        if tag_str == "":
            dot = ""
        if translation_tag == "":
            tag_str = tag_str + dot + origin_tag
        else:
            tag_str = tag_str + dot + origin_tag + "/" + translation_tag

    return tag_str


def validate_permission(session: Uninfo) -> bool:
    group_id = session.group.id
    if len(WORK_GROUP_LIST) > 0:
        if group_id in WORK_GROUP_LIST:
            return True
        return False
    if len(FILTER_GROUP_LIST) > 0:
        if group_id in FILTER_GROUP_LIST:
            return False
        return True
    return True


def create_text_image(text_content: str, width: int = 800, height: int = 600) -> bytes | None:
    """
    根据给定的文本内容创建一张图片，并返回其二进制数据。

    Args:
        text_content (str): 要显示在图片上的文字。
        width (int): 图片宽度。
        height (int): 图片高度。

    Returns:
        bytes | None: 成功时返回图片的PNG格式二进制数据，失败则返回None。
    """
    try:
        # 确定字体文件路径 (假设字体文件和 __init__.py 在同一目录)
        font_path = os.path.join(os.path.dirname(__file__), "msyh.ttc")  # <--- 修改为您自己的字体文件名

        # 加载字体，如果找不到则使用Pillow默认字体（不支持中文）
        try:
            font = ImageFont.truetype(font_path, size=24)
        except IOError:
            logger.warning(f"字体文件未找到: {font_path}，将使用默认字体（可能无法显示中文）")
            font = ImageFont.load_default()

        # 创建一张白色背景的图片
        image = Image.new("RGB", (width, height), "white")
        draw = ImageDraw.Draw(image)

        # 计算文字应放置的位置（居中）
        # 使用 textbbox 获取精确的边界框
        text_bbox = draw.textbbox((0, 0), text_content, font=font)
        text_width = text_bbox[2] - text_bbox[0]
        text_height = text_bbox[3] - text_bbox[1]
        position = ((width - text_width) / 2, (height - text_height) / 2)

        # 将文字绘制到图片上
        draw.text(position, text_content, fill="black", font=font)

        # 将图片保存到内存中的二进制IO流
        img_byte_arr = io.BytesIO()
        image.save(img_byte_arr, format='PNG')

        # 返回二进制数据
        return img_byte_arr.getvalue()

    except Exception as e:
        logger.error(f"创建文本图片时发生错误: {e}")
        return None


async def compress_image(
        image_path: str,
        target_kb: int = 12 * 1024,  # 目标大小 12MB
        quality: int = 90,  # 初始 JPEG 质量
        step: int = 5,  # 每次迭代降低的质量值
        min_quality: int = 70,  # 最低 JPEG 质量
        max_iterations: int = 5,  # 最大迭代次数，防止死循环
        safety_margin: float = 0.90  # 初始缩放的安全系数
):
    """
    通过迭代预测和修正，智能地将图片压缩到目标大小以下。

    策略:
    1. 检查初始大小。
    2. (仅JPEG) 尝试逐步降低质量来达到目标，这是最快的无损尺寸方式。
    3. 如果降质后仍过大，进行一次基于比例的智能缩放（带安全系数）。
    4. 如果仍然过大，进入快速修正循环，每次按一定比例缩小，直到达标或达到最大迭代次数。
    """
    target_size = target_kb * 1024

    try:
        # --- 步骤 1: 检查初始大小 ---
        if await asyncio.to_thread(os.path.getsize, image_path) <= target_size:
            logger.info("原图片已小于目标大小，无需压缩。")
            return True

        async with aiofiles.open(image_path, 'rb') as f:
            content = await f.read()

        img = await asyncio.to_thread(Image.open, io.BytesIO(content))

        # 修正图片方向
        if ImageOps:
            img = await asyncio.to_thread(ImageOps.exif_transpose, img)

        current_quality = quality

        # --- 步骤 2: (仅JPEG) 优先尝试降低质量 ---
        if img.format == 'JPEG':
            logger.info("检测到JPEG格式，优先尝试降低质量...")
            for q in range(quality, min_quality - 1, -step):
                buffer = io.BytesIO()
                await asyncio.to_thread(img.save, buffer, format='JPEG', quality=q, optimize=True)
                current_content = buffer.getvalue()
                if len(current_content) <= target_size:
                    logger.info(f"通过降低质量到 {q} 成功将图片压缩到目标大小。")
                    async with aiofiles.open(image_path, 'wb') as f:
                        await f.write(current_content)
                    return True
            content = current_content  # 使用降质后的内容进行下一步
            logger.info(f"质量降低至 {min_quality} 后，文件大小仍过大。准备缩放尺寸...")

        # --- 步骤 3 & 4: 智能缩放与快速修正循环 ---
        current_size = len(content)
        img = await asyncio.to_thread(Image.open, io.BytesIO(content))  # 重新加载降质后的图片

        for i in range(max_iterations):
            if current_size <= target_size:
                logger.info(f"在第 {i + 1} 次迭代中成功达到目标大小。")
                break

            # 核心：计算缩放比例
            # 第一次迭代使用带安全系数的预测，后续迭代在前一次基础上微调
            if i == 0:
                scale = (target_size / current_size) ** 0.5 * safety_margin
            else:
                scale = 0.9  # 后续迭代，每次缩小10%的尺寸

            new_width = int(img.width * scale)
            new_height = int(img.height * scale)

            if new_width < 1 or new_height < 1:
                logger.warning("图片尺寸已缩到最小，无法继续压缩。")
                return False

            logger.info(f"迭代 {i + 1}/{max_iterations}: 缩放比例 {scale:.2f}，目标尺寸 {new_width}x{new_height}")

            # 在线程中执行耗时的 resize 和 save
            resized_img = await asyncio.to_thread(img.resize, (new_width, new_height))

            buffer = io.BytesIO()
            img_format = img.format or 'JPEG'
            q = current_quality if img_format == 'JPEG' else 95
            await asyncio.to_thread(resized_img.save, buffer, format=img_format, quality=q, optimize=True)

            content = buffer.getvalue()
            current_size = len(content)
            img = resized_img  # 更新img对象为缩放后的，用于下一次迭代

        else:  # for-else 结构，如果循环正常结束（未被break），则执行
            logger.warning(f"达到最大迭代次数 {max_iterations} 后，文件大小仍超过目标。")
            return False

        # --- 最终写入 ---
        async with aiofiles.open(image_path, 'wb') as f:
            await f.write(content)

        final_size_kb = len(content) / 1024
        logger.info(f"图片压缩成功。最终大小: {final_size_kb:.2f} KB，尺寸: {img.width}x{img.height}")
        return True

    except Exception as e:
        logger.error(f"图片压缩失败: {e}", exc_info=e)
        return False


class UgoiraException(Exception):
    def __init__(self, *args):
        super().__init__(*args)


async def convert_ugoira_zip_to_gif(
        zip_path: str,
        frames_data: list,
        output_gif_path: str
) -> bool:
    """
    将 Pixiv Ugoira 的 ZIP 文件根据 frames 元数据合成为 GIF。

    :param zip_path: 输入的 ugoira zip 文件路径。
    :param frames_data: 从 Pixiv API 获取的 frames 列表。
    :param output_gif_path: 输出的 GIF 文件路径。
    :return: 成功返回 True，失败返回 False。
    """
    logger.info(f"开始转换 Ugoira 文件: {zip_path}")

    def process_zip():
        pil_frames = []
        try:
            with zipfile.ZipFile(zip_path, 'r') as zf:
                for frame_info in frames_data:
                    frame_filename = frame_info['file']
                    with zf.open(frame_filename) as frame_file:
                        frame_bytes = frame_file.read()
                        img = Image.open(io.BytesIO(frame_bytes)).convert("RGB")
                        img = img.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE)
                        pil_frames.append(img)

            if not pil_frames:
                logger.error("未能从ZIP文件中加载任何帧。")
                return False

            # 使用第一帧作为基础，附加其余帧来创建GIF
            # duration 是每一帧的毫秒数
            # loop=0 表示无限循环
            pil_frames[0].save(
                output_gif_path,
                save_all=True,
                append_images=pil_frames[1:],
                duration=[frame['delay'] for frame in frames_data],
                loop=0,
                optimize=False,  # 关闭压缩优化
                disposal=2,
                lossless=True
            )
            logger.info(f"成功将 Ugoira 转换为 GIF: {output_gif_path}")
            return True
        except Exception as e:
            logger.error(f"转换 Ugoira 动图失败: {e}", exc_info=e)
            return False

    return await asyncio.to_thread(process_zip)


async def package_file_to_zip(
        source_file_path: str,
        zip_file_path: str,
        archive_name: str = None
) -> bool:
    """
    异步地将单个文件打包到一个 ZIP 压缩包中。

    :param source_file_path: 要打包的源文件路径。
    :param zip_file_path: 输出的 ZIP 文件路径。
    :param archive_name: 文件在 ZIP 压缩包中的名字。如果为 None，则使用源文件名。
    :return: 成功返回 True，失败返回 False。
    """
    logger.info(f"开始将文件 '{os.path.basename(source_file_path)}' 打包到 '{os.path.basename(zip_file_path)}'")

    # 这是将在后台线程中运行的同步函数
    def _create_zip():
        try:
            # 如果没有指定压缩包内的文件名，就使用源文件的基本名称
            arcname = archive_name or os.path.basename(source_file_path)

            # 使用 'w' 模式创建并写入ZIP文件，ZIP_DEFLATED 表示使用压缩
            with zipfile.ZipFile(zip_file_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                zf.write(source_file_path, arcname=arcname)

            logger.info(f"文件成功打包: {zip_file_path}")
            return True
        except FileNotFoundError:
            logger.error(f"打包失败：源文件未找到 '{source_file_path}'")
            return False
        except Exception as e:
            logger.error(f"打包文件时发生未知错误: {e}", exc_info=e)
            return False

    return await asyncio.to_thread(_create_zip)

async def create_user_display_image(
        bg_image_A: str | None,
        avatar_image_B: str | None,
        artwork_images_W: list[str],
        author_name: str,
        current_page: int,
        total_pages: int,
        total_width: int = 2000
) -> Image.Image:
    """
    将用户的主页背景、头像、作品集和页码整合到一张图片中。(V3)
    - 新增作品网格区域的圆角背景。
    """

    # --- 内部辅助函数定义 (无变动) ---

    def _crop_top_square(image: Image.Image) -> Image.Image:
        """从图片顶部中心裁剪出最大的正方形。"""
        w, h = image.size
        side = min(w, h)
        left = (w - side) // 2
        top = 0
        right = left + side
        bottom = side
        return image.crop((left, top, right, bottom))

    def _crop_to_circle(image: Image.Image) -> Image.Image:
        """将正方形图片裁剪为圆形。"""
        mask = Image.new('L', image.size, 0)
        draw = ImageDraw.Draw(mask)
        draw.ellipse((0, 0) + image.size, fill=255)

        result = image.copy()
        result.putalpha(mask)
        return result

    def _create_rounded_rectangle_mask(size: tuple[int, int], radius: int) -> Image.Image:
        """创建一个顶部为圆角的遮罩。"""
        mask = Image.new('L', size, 0)
        draw = ImageDraw.Draw(mask)
        draw.rounded_rectangle((0, 0, size[0], size[1] * 2), radius=radius, fill=255)
        return mask

    async def _process_artwork_image(image_path: str, box_size: int, radius: int) -> Image.Image:  # 新增 radius 参数
        """(异步)处理单个作品图：读取、缩放并放置在带圆角背景的方块中。"""
        try:
            async with aiofiles.open(image_path, 'rb') as f:
                content = await f.read()
            image = await asyncio.to_thread(Image.open, io.BytesIO(content))
            image = image.convert("RGBA")  # 确保图片有Alpha通道
        except FileNotFoundError:
            # 如果文件不存在，创建一个占位图
            image = Image.new("RGBA", (box_size // 2, box_size // 2), "#C0C0C0")

        original_w, original_h = image.size
        if original_w == 0 or original_h == 0:  # 处理无效图片
            image = Image.new("RGBA", (box_size // 2, box_size // 2), "#C0C0C0")
            original_w, original_h = image.size

        # 1. 创建一个完全透明的背景画布
        rounded_bg = Image.new("RGBA", (box_size, box_size), (255, 255, 255, 0))
        draw = ImageDraw.Draw(rounded_bg)

        # 2. 在透明画布上绘制一个带颜色的圆角矩形
        inset = 2  # 内缩1个像素
        draw.rounded_rectangle(
            (inset, inset, box_size - inset, box_size - inset),
            radius=radius,
            fill="#F0F0F0"  # 背景色
        )

        # 3. 缩放作品图以适应背景 (可以稍微缩小一点留出内边距)
        inner_box_size = box_size - int(box_size * 0.05)  # 留出5%的内边距
        ratio = min(inner_box_size / original_w, inner_box_size / original_h)
        new_w, new_h = int(original_w * ratio), int(original_h * ratio)
        resized_image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # 4. 将缩放后的图片居中粘贴到圆角背景上
        paste_x = (box_size - new_w) // 2
        paste_y = (box_size - new_h) // 2
        # 使用 resized_image 作为遮罩，以保留作品图自身的透明度
        rounded_bg.paste(resized_image, (paste_x, paste_y), resized_image)

        return rounded_bg

    def _generate_page_list(c_page: int, t_pages: int) -> list:
        """根据当前页和总页数，生成用于显示的页码列表（带省略号）。"""
        if t_pages <= 7:
            return list(range(1, t_pages + 1))
        page_list = [1]
        if c_page > 4: page_list.append('...')
        start = max(2, c_page - 1)
        end = min(t_pages - 1, c_page + 1)
        for i in range(start, end + 1): page_list.append(i)
        if c_page < t_pages - 3: page_list.append('...')
        page_list.append(t_pages)
        return page_list

    def _draw_pagination(draw: ImageDraw.Draw, x: int, y: int, width: int, p_list: list, c_page: int, scale: float):
        """(新) 在指定位置居中绘制页码，当前页为圆形灰底白字。"""
        try:
            font_size = int(32 * scale)
            font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "msyh.ttc"), size=font_size)
        except IOError:
            font = ImageFont.load_default()
            font_size = 20

        page_items = [str(p) for p in p_list]
        item_widths = [draw.textlength(p, font=font) for p in page_items]
        spacing = int(20 * scale)

        total_text_width = sum(item_widths) + spacing * (len(page_items) - 1 if page_items else 0)
        current_x = x + (width - total_text_width) / 2

        for i, page in enumerate(page_items):
            item_width = item_widths[i]
            text_x = current_x
            text_y = y + int(5 * scale)

            if str(page) == str(c_page):
                circle_radius = int(font_size * 0.8)
                center_x = text_x + item_width / 2
                center_y = text_y + font_size / 2
                draw.ellipse(
                    (center_x - circle_radius, center_y - circle_radius,
                     center_x + circle_radius, center_y + circle_radius),
                    fill="#808080"
                )
                draw.text((text_x, text_y), page, font=font, fill="white")
            else:
                draw.text((text_x, text_y), page, font=font, fill="black")
            current_x += item_width + spacing

    # --- 1. 动态尺寸计算 ---
    scale_factor = total_width / 2000.0
    avatar_size = int(200 * scale_factor)
    author_name_font_size = int(40 * scale_factor)
    artwork_box_size = int(194.5 * scale_factor)
    artwork_corner_radius = int(15 * scale_factor)
    gap = int(5 * scale_factor)
    main_corner_radius = int(50 * scale_factor)
    grid_corner_radius = int(20 * scale_factor)  # 网格背景的圆角半径
    pagination_margin_top = int(50 * scale_factor)
    pagination_height = int(60 * scale_factor)

    # --- 2. 异步加载和处理所有图片 ---
    bg_image, avatar_image, scaled_artworks_W = await asyncio.gather(
        (lambda p: asyncio.to_thread(Image.open, p) if p else asyncio.sleep(0, result=None))(bg_image_A),
        (lambda p: asyncio.to_thread(Image.open, p) if p else asyncio.sleep(0, result=None))(avatar_image_B),
        asyncio.gather(*[_process_artwork_image(p, artwork_box_size, artwork_corner_radius) for p in artwork_images_W])
    )

    # --- 3. 进一步处理背景和头像 ---
    scaled_bg_A = None
    bg_A_h = int(450 * scale_factor)
    if bg_image:
        bg_image = bg_image.convert("RGBA")
        scaled_bg_A = bg_image.resize((total_width, int(bg_image.height * total_width / bg_image.width)),
                                      Image.Resampling.LANCZOS)
        bg_A_h = scaled_bg_A.height

    circular_avatar = None
    if avatar_image:
        avatar_image = avatar_image.convert("RGBA")
        square_avatar = _crop_top_square(avatar_image)
        resized_avatar = square_avatar.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
        circular_avatar = _crop_to_circle(resized_avatar)

    # --- 4. 布局计算 ---
    overlap_height = min(int(bg_A_h * 0.2), int(100 * scale_factor))
    white_area_y = bg_A_h - overlap_height

    avatar_y = white_area_y - avatar_size // 2
    avatar_x = (total_width - avatar_size) // 2

    temp_draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    try:
        author_font = ImageFont.truetype(os.path.join(os.path.dirname(__file__), "msyh.ttc"), size=author_name_font_size)
    except IOError:
        author_font = ImageFont.load_default()

    author_name_bbox = temp_draw.textbbox((0, 0), author_name, font=author_font)
    author_name_width = author_name_bbox[2] - author_name_bbox[0]
    author_name_height = author_name_bbox[3] - author_name_bbox[1]

    author_name_x = (total_width - author_name_width) // 2
    author_name_y = avatar_y + avatar_size + int(15 * scale_factor)

    grid_start_y = author_name_y + author_name_height + int(40 * scale_factor)

    num_rows = math.ceil(len(scaled_artworks_W) / 10)
    grid_height = num_rows * (artwork_box_size + gap) - (gap if num_rows > 0 else 0)

    # 【新增】计算网格背景的精确尺寸和位置
    grid_bg_x = gap
    grid_bg_y = grid_start_y
    grid_bg_width = total_width - 2 * gap
    grid_bg_height = grid_height

    pagination_y = grid_start_y + grid_height + pagination_margin_top

    # --- 5. 计算总高度并创建画布 ---
    total_height = grid_start_y + grid_height
    if total_pages > 1:
        total_height += pagination_margin_top + pagination_height

    final_image = Image.new("RGBA", (total_width, total_height), "white")
    draw = ImageDraw.Draw(final_image)

    # --- 6. 按层级绘制 ---
    # (1) 绘制背景
    if scaled_bg_A:
        final_image.paste(scaled_bg_A, (0, 0))

    # (2) 绘制带圆角的白色内容区域
    white_area_height = total_height - white_area_y
    white_area = Image.new("RGBA", (total_width, white_area_height), "white")
    mask = _create_rounded_rectangle_mask(white_area.size, main_corner_radius)
    final_image.paste(white_area, (0, white_area_y), mask)

    # # (3) 【新增】绘制圆角作品网格背景
    # if scaled_artworks_W:  # 只有在有作品时才绘制背景
    #     draw.rounded_rectangle(
    #         (grid_bg_x, grid_bg_y, grid_bg_x + grid_bg_width, grid_bg_y + grid_bg_height),
    #         radius=grid_corner_radius,
    #         fill="#F0F0F0"  # 与单个作品背景色一致
    #     )

    # (4) 粘贴作品网格
    for i, artwork in enumerate(scaled_artworks_W):
        row, col = i // 10, i % 10
        artwork_x = gap + col * (artwork_box_size + gap)
        artwork_y = grid_start_y + row * (artwork_box_size + gap)
        final_image.paste(artwork, (artwork_x, artwork_y), artwork)

    # (5) 粘贴圆形头像
    if circular_avatar:
        final_image.paste(circular_avatar, (avatar_x, avatar_y), circular_avatar)

    # (6) 绘制作者名
    draw.text((author_name_x, author_name_y), author_name, font=author_font, fill="black")

    # (7) 绘制页码
    if total_pages > 1:
        page_list_to_display = _generate_page_list(current_page, total_pages)
        _draw_pagination(draw, 0, pagination_y, total_width, page_list_to_display, current_page, scale_factor)

    return final_image.convert("RGB")
