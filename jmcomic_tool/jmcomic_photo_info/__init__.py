from jmcomic import JmOption
from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo
from zhenxun.configs.utils import BaseBlock, PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils

__plugin_meta__ = PluginMetadata(
    name="Jm章节",
    description="懂的都懂，密码是id号",
    usage="""
    指令：
        jm章节 [本子id]
        jm章节 [章节id]
    示例：
        jm章节 114514
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

_info_matcher = on_alconna(
    Alconna("jm章节", Args["album_id", str]), priority=5, block=True, rule=to_me()
)


@_info_matcher.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma, album_id: str):
    op = JmOption.default()
    cl = op.new_jm_client()
    album = cl.get_album_detail(album_id)
    episode_list = sorted(album.episode_list, key=lambda x: int(x[1]))
    if len(episode_list) == 1:
        await (MessageUtils.build_message([f'本子信息:\n'
                                           f'* [{album.id}]\n'
                                           f'* {album.authoroname}\n'
                                           f'没有其他章节\n'
                                           f'本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev'])
               .send(reply_to=True))
        logger.info(f"本子信息 {album_id}", arparma.header_result, session=session)
        return
    # 构造章节信息
    photo_id = ""
    photo_curr = ""
    photo_title = ""
    photo_num = len(album.episode_list)
    for i, value in enumerate(episode_list):
        # 章节编号
        photo_id = value[0]
        if photo_id == album_id:
            # 章节序号
            photo_curr = value[1]
            # 章节标题
            photo_title = value[2]
            break
    # 获取本子信息(第一个章节的信息)
    real_album_id = episode_list[0][0]
    real_album = cl.get_album_detail(real_album_id)

    # 构造全部章节信息
    photo_info_str = ""
    for i, value in enumerate(episode_list):
        # 章节编号
        id = value[0]
        # 章节序号
        curr = value[1]
        # 章节标题
        title = value[2]
        photo_info_str = photo_info_str + f'[{id}] 第{curr}章 {title}\n'

    await (MessageUtils.build_message([f'本子信息:\n'
                                       f'* [{real_album.id}]\n'
                                       f'* {real_album.authoroname}\n'
                                       f'本子章节信息 [{album_id}]:\n'
                                       f'* 章节标题: {photo_title}\n'
                                       f'* 当前为第 {photo_curr} 章, 总章节数: {photo_num}\n'
                                       f'{photo_info_str}\n'
                                       f'本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev'])
           .send(reply_to=True))
    logger.info(f"本子信息 {album_id}", arparma.header_result, session=session)
