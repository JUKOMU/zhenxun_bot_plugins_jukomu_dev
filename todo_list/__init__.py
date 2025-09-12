from arclet.alconna import Arg
from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginExtraData

__plugin_meta__ = PluginMetadata(
    name="待办列表",
    description="显示当前Bot的待办事项列表",
    usage="""
    指令：
        Todo
        待办
        待办列表
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="todolist",
    ).to_dict(),
)

_info_matcher1 = on_alconna(
    Alconna("Todo"), priority=5, block=True, rule=to_me()
)

_info_matcher2 = on_alconna(
    Alconna("待办"), priority=5, block=True, rule=to_me()
)

_info_matcher3 = on_alconna(
    Alconna("待办列表"), priority=5, block=True, rule=to_me()
)

_add_matcher = on_alconna(
    Alconna("添加待办", Args["content", str], separators=' '), priority=5, block=True, rule=to_me()
)

_change_matcher1 = on_alconna(
    Alconna("更改顺序", Args[Arg("id", int), Arg("index", int)], separators=' '), priority=5, block=True, rule=to_me()
)

_change_matcher2 = on_alconna(
    Alconna("更改状态", Args[Arg("id", int), Arg("status", str)], separators=' '), priority=5, block=True, rule=to_me()
)


@_info_matcher1.handle()
@_info_matcher2.handle()
@_info_matcher3.handle()
async def _(bot: Bot, session: Uninfo, arparma: Arparma):
    """
    获取待办列表
    """
    pass


@_add_matcher.handle()
async def __(bot: Bot, session: Uninfo, arparma: Arparma, content: str):
    """
    添加待办
    """
    pass


@_change_matcher1.handle()
async def ___(bot: Bot, session: Uninfo, arparma: Arparma, id: int, index: int):
    """
    改变待办顺序
    """
    pass

@_change_matcher2.handle()
async def ____(bot: Bot, session: Uninfo, arparma: Arparma, id: int, status: str):
    """
    改变待办状态
    """
    pass
