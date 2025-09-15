import re

from nonebot.adapters.onebot.v11 import Bot, MessageEvent
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

from .data_source import JmDownload

__plugin_meta__ = PluginMetadata(
    name="Jm下载器",
    description="懂的都懂，密码是id号",
    usage="""
    指令1：
        jm [本子id]
    示例1：
        jm 114514
    指令2：
        对Jm信息回复"@机器人 下载"会下载该信息jm号对应的本子
        见"Jm信息"插件
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="jmcomic",
        limits=[
            BaseBlock(result="当前有本子正在下载，请稍等..."),
            PluginCdBlock(result="Jm下载器冷却中（5s）..."),
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("jm", Args["album_id", str]), priority=5, block=True, rule=to_me()
)

_info_matcher = on_alconna(
    Alconna("下载"), priority=5, block=True, rule=to_me()
)


@_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, album_id: str):
    await MessageUtils.build_message("正在下载中，请稍后...\n"
                                     f"本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev").send(
        reply_to=True)
    group_id = session.group.id if session.group else None
    await JmDownload.download_album(bot, session.user.id, group_id, album_id)
    logger.info(f"下载了本子 {album_id}", arparma.header_result, session=session)


@_info_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, event: MessageEvent):
    msg = await bot.get_msg(message_id=event.message_id)
    # 获取消息内容
    match = re.search(r'\[CQ:reply,id=(\d+)\]', msg.get('raw_message'))
    reply_msg = await bot.get_msg(message_id=match.group(1))
    text_content = None
    for item in reply_msg.get('message'):
        if item['type'] == 'text':
            text_content = item['data']['text']
            break
    if text_content:
        # 获取jm号
        match = re.search(r'\* \[(\d+)\]', text_content)
        if match:
            album_id = match.group(1)
            await MessageUtils.build_message("正在下载中，请稍后...\n"
                                             f"本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev").send(
                reply_to=True)
            group_id = session.group.id if session.group else None
            await JmDownload.download_album(bot, session.user.id, group_id, album_id)
            logger.info(f"下载了本子 {album_id}", arparma.header_result, session=session)
