import configparser
import os
import time
from pathlib import Path
import img2pdf
import html2text
import requests
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
         获取所有插画
          pid 90457556 all
        2.
         解析pid=90457556的作品信息, 包含第一张插画的图片直链
          pinfo 90457556
         解析pid=90457556的作品信息, 包含第二张插画的图片直链
          pinfo 90457556 2
        3.
         获取画师简要信息, 画师主页, 画师作品数量
          puser 16985944
        4.
         获取id=16985944的画师信息, 默认前50个作品, 返回html文件
          puser-d 16985944
         获取id=16985944的画师信息, 前100个作品, 返回html文件
          puser-d 16985944 100
         获取id=16985944的画师信息, 所有作品, 返回html文件
          puser-d 16985944 all
         获取id=16985944的画师信息, 默认前50个作品, 返回图片
          puser-d 16985944 img
         获取id=16985944的画师信息, 前100个作品, 返回图片
          puser-d 16985944 100 img
         获取id=16985944的画师信息, 所有作品, 返回图片
          puser-d 16985944 all img
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
    Alconna("pid", Args[Arg("illust_id", str), Arg("index?", str)], separators=' '), priority=5, block=True
)

_info_matcher2 = on_alconna(
    Alconna("pinfo", Args[Arg("illust_id", str), Arg("index?", str)], separators=' '), priority=5, block=True
)

_info_matcher3 = on_alconna(
    Alconna("puser", Args["user_id", str], separators=' '), priority=5, block=True
)

_info_matcher4 = on_alconna(
    Alconna("puser-d", Args[Arg("user_id", str), Arg("num?", int), Arg("type?", str)], separators=' '), priority=5, block=True
)

_update_matcher = on_alconna(
    Alconna("pid更新凭证", Args["token", str], separators=' '), priority=5, block=True
)


def call_proxy(method: str, target_url: str, query_params=None | dict, json_body=None | dict,
               custom_headers=None | dict, cookies=None | dict,
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
async def _(bot: Bot, session: Uninfo, arparma: Arparma, illust_id: str, index: Match[str]):
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
    image_url: str = ""
    # 标题
    tile = None
    # 页数
    pages = None
    # 页码
    page_no = None
    # 图片代理链接
    image_url_proxy = ""
    if metadata_response:
        # 解析图片信息
        try:
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
                if not index.result:
                    # 页码无效
                    return
                page_no = index.result

            # if page_no != "1" and page_no != "all":
            #     image_url = image_url.replace("_p0", f"_p{int(page_no) - 1}")

            image_url_proxy = image_url.replace("i.pximg.net", "i.pixiv.cat")

        except Exception:
            await MessageUtils.build_message(["解析失败"]).send(reply_to=True)
            logger.info("pid解析失败")
    # 构建页码表
    page_nos = []
    # 构建回复信息
    msg = []
    try:
        if page_no != "all":
            page_nos.append(page_no)
        else:
            page_nos = [str(x) for x in int(pages)]
        for page_no in page_nos:
            suffix = ""
            if pages > 1:
                suffix = f"-{page_no}"
            output_filename = f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
            path = Path() / f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
            if not path.exists():
                image_url_proxy_2 = image_url_proxy.replace("_p0", f"_p{int(page_no) - 1}")
                # 下载图片
                image_bytes = call_proxy(
                    method="GET",
                    target_url=image_url_proxy_2,
                    return_format='binary'
                )
                if not image_bytes:
                    raise Exception()
                # 将获取到的二进制数据保存为文件
                try:
                    with open(output_filename, "wb") as f:
                        f.write(image_bytes)
                    logger.info(f"pid图片保存成功: {illust_id}")
                except IOError as e:
                    logger.error(f"pid图片保存失败, {e}")
                    raise Exception()
            msg.append(path)
        msg.append("\n")
        msg.append(f"{tile}\n* 作者: {author_name}/{author_id}\n{page_no}/{pages}")
    except Exception:
        logger.error(f"pid获取图片失败: {illust_id}")

    # 发送图片
    try:
        await MessageUtils.build_message(msg).send(reply_to=False)
        logger.info(f"pid解析 {illust_id}", arparma.header_result, session=session)
    except Exception:
        # 发送失败(大概率是吞图了)
        # 使用pdf发送
        # 检查文件是否存在
        files = []
        pdf_file = ""
        path = None
        try:
            if page_no != "all":
                suffix = ""
                if pages > 1:
                    suffix = f"-{page_no}"
                pdf_file = f"{BASE_PATH}/{illust_id}{suffix}{flag}.pdf"
            else:
                pdf_file = f"{BASE_PATH}/{illust_id}{flag}-all.pdf"
            path = Path() / pdf_file
            if not path.exists():
                # 文件不存在
                raise Exception()
        except Exception:
            for page_no in page_nos:
                suffix = ""
                if pages > 1:
                    suffix = f"-{page_no}"
                output_filename = f"{BASE_PATH}/{illust_id}{suffix}{flag}.png"
                files.append(output_filename)
            # 生成pdf
            with open(pdf_file, "wb") as f:
                f.write(img2pdf.convert(files))
        if session.group.id:
            await bot.call_api(
                "upload_group_file",
                group_id=session.group.id,
                file=f"file:///{path.absolute()}",
                name=f"{pdf_file}",
            )
        else:
            await bot.call_api(
                "upload_private_file",
                user_id=session.user.id,
                file=f"file:///{path.absolute()}",
                name=f"{pdf_file}",
            )

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
async def ____(bot: Bot, session: Uninfo, arparma: Arparma, user_id: str, num: Match[int], type: Match[str]):
    if session.group:
        if not validate_permission(session):
            return
    number = 50
    type_str = "html"
    if num.available:
        if str(num.result).isdigit():
            # 数量有效
            number = num.result
        else:
            # 不是有效数字, 验证是否信息类型
            if str(num.result) == "html" or str(num.result) == "img":
                type_str = str(num.result)

        if type.available:
            # 验证是否信息类型
            if str(num.result) == "html" or str(num.result) == "img":
                type_str = str(num.result)


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