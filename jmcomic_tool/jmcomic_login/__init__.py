from arclet.alconna.args import Arg
from jmcomic import *
from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.models.jm_account import JmAccount
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="Jm登录",
    description="登录你的JM账号",
    usage="""
    指令：
        jm登录 [用户名] [密码]
    示例：
        jm登录 tom 114514
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="jmcomic",
        limits=[
            BaseBlock(result="请稍等..."),
            PluginCdBlock(result="Jm登录冷却中（5s）..."),
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("jm登录", Args[Arg("username", str), Arg("password", str)], separators=' '), priority=5, block=True,
    rule=to_me()
)


@_matcher.handle()
async def _(bot: Bot,
            session: Uninfo,
            arparma: Arparma,
            username: str,
            password: str,
            event: MessageEvent):
    # 禁止群聊登录
    if session.group:
        await MessageUtils.build_message(["不要在群聊中输入自己的账号密码"]).send(reply_to=True)
        await bot.delete_msg(message_id=event.message_id)
        logger.info(f"禁止了一个从群聊的jm登录", arparma.header_result, session=session)
        return

    option = JmOption.default()
    client_jm = option.new_jm_client()

    try:
        resp = client_jm.login(username, password)
        if resp.http_code != 200:
            raise ResponseUnexpectedException("登录失败", {})
        resp_json = json_loads(resp.decoded_data)
        uid = session.user.id
        # 存储
        await JmAccount.update_user(username, password, uid)
        await MessageUtils.build_message([f'JM登录成功\n'
                                          f'用户：{username}\n'
                                          f'coin：{resp_json.get("coin")}\n'
                                          f'level：{resp_json.get("level_name")}']).send(reply_to=True)
    except ResponseUnexpectedException as e:
        logger.error(f"JM登录失败", arparma.header_result, session=session)
        # 登录失败
        await MessageUtils.build_message(["JM登录失败，请稍后重试"]).send(reply_to=True)

    logger.info(f"jm登录 {username}", arparma.header_result, session=session)
