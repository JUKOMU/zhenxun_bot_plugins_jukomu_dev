from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna, Match
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import PluginExtraData
from zhenxun.models.jm_account import JmAccount
from zhenxun.utils.message import MessageUtils
from zhenxun.utils.platform import PlatformUtils

from .data_source import *

__plugin_meta__ = PluginMetadata(
    name="Jm收藏夹",
    description="获取你Jm账号的收藏夹",
    usage="""
    指令：
        jm收藏夹 ?[页码]
        jm收藏夹 更新
    示例：
        jm收藏夹: 默认获取收藏夹第一页
        jm收藏夹 2: 获取收藏夹第二页
        jm收藏夹 更新: 更新你的收藏夹
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="jmcomic",
    ).to_dict(),
)

"""
page -> int 获取对应页码的收藏夹
page -> str -> "更新收藏夹"
"""
_matcher = on_alconna(
    Alconna("jm收藏夹", Args["page?", str]), priority=5, block=True, rule=to_me()
)


async def _handle_send(log_meg: str, arparma, session, *send_meg):
    await (MessageUtils.build_message(list(send_meg)).send(reply_to=True))
    logger.info(log_meg, arparma.header_result, session=session)


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, page: Match[int]):
    # 判断是否拥有账号
    uid = session.user.id
    jm_account = await JmAccount.get_user(uid)
    if jm_account.id == -1:
        # 没有账号,提示用户登录
        await _handle_send("用户未登录，提示用户登录", arparma, session, "你还没有登录jm哦，请重新登录")
        return
    # 获取用户名和密码
    jm_username = jm_account.username
    jm_password = jm_account.password

    # 获取用户QQ头像
    ava_url = PlatformUtils.get_user_avatar_url(uid, "qq", session.self_id)
    resp = await asyncio.to_thread(
        handle_request,
        ava_url,
        "GET")
    avatar: bytes = resp.content

    """
        不带参数，默认参数，获取收藏夹第一页
    """
    if not page.available:
        # 获取已缓存的图片
        path = Path() / f"{BASE_PATH}/{uid}_{1}.png"
        if path.exists():
            await _handle_send(f"jm收藏夹 {uid}, page {1}", arparma, session, path)
            return
        # 没有缓存
        fpage = await JmFavouritePage(uid, 1, jm_username, jm_password).async_init()
        fpage.set_avatar(avatar)
        if not fpage.check():
            return
        # 生成收藏夹信息图片
        img = await fpage.create_page_img()
        img.save(path.absolute())
        # 发送图片
        await _handle_send(f"jm收藏夹 {uid}, page {1}", arparma, session, path)
        return

    """
        带参数，page -> “更新”
    """
    # 带参数，检查参数
    page_result = str(page.result)
    # page -> “更新”
    if page_result == "更新":
        # 删除缓存图片
        if await JmFavouritePage.clear_cache(uid):
            await _handle_send(f"jm收藏夹更新成功,uid: {uid}", arparma, session, "已删除缓存")
        else:
            await _handle_send(f"jm收藏夹更新失败,uid: {uid}", arparma, session, "更新失败")
        return
    # page -> not int 非法参数
    if not page_result.isdigit():
        return

    """
        带参数，page -> int
    """
    # 获取已缓存的图片
    path = Path() / f"{BASE_PATH}/{uid}_{page_result}.png"
    if path.exists():
        await _handle_send(f"jm收藏夹 {uid}, page {page_result}", arparma, session, path)
        return
    # 没有缓存
    fpage = await JmFavouritePage(uid, int(page_result), jm_username, jm_password).async_init()
    fpage.set_avatar(avatar)
    if fpage.check():
        # 生成收藏夹信息图片
        img = await fpage.create_page_img()
        img.save(path.absolute())
        # 发送图片
        await _handle_send(f"jm收藏夹 {uid}, page {page_result}", arparma, session, path)
        return
