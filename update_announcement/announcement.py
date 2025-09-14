from enum import Enum

from tortoise import Tortoise
from tortoise import fields
from zhenxun.services.db_context import Model
from zhenxun.services.log import logger


class AnnouncementType(Enum):
    """
    公告类型。
    """

    NEW_FEATURE = 'feat'
    IMPROVEMENT = 'impr'
    BUG_FIX = 'fix'
    SECURITY_UPDATE = 'security'
    PERFORMANCE_UPDATE = 'perf'
    GENERAL = 'chore'
    DOCUMENTATION = 'docs'
    DEPRECATION_WARNING = 'depr'

    @classmethod
    def description(cls, value: str, default: str = "未知类型") -> str:
        """
        通过成员的值（简短标识符）获取其对应的描述。

        Args:
            value: 要查找的简短标识符 (例如 'feat')。
            default: 如果未找到对应的值，返回的默认字符串。

        Returns:
            对应的描述字符串，如果未找到则返回默认值。
        """
        if value == cls.NEW_FEATURE:
            return '新功能'
        if value == cls.IMPROVEMENT:
            return '功能改进'
        if value == cls.BUG_FIX:
            return '问题修复'
        if value == cls.SECURITY_UPDATE:
            return '安全更新'
        if value == cls.PERFORMANCE_UPDATE:
            return '性能优化'
        if value == cls.GENERAL:
            return '常规公告'
        if value == cls.DOCUMENTATION:
            return '文档更新'
        if value == cls.DEPRECATION_WARNING:
            return '废弃警告'
        return default


announcement_type_list = [AnnouncementType.NEW_FEATURE, AnnouncementType.IMPROVEMENT, AnnouncementType.BUG_FIX,
                          AnnouncementType.SECURITY_UPDATE, AnnouncementType.PERFORMANCE_UPDATE,
                          AnnouncementType.GENERAL, AnnouncementType.DOCUMENTATION,
                          AnnouncementType.DEPRECATION_WARNING]

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS announcements
(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "type" TEXT NOT NULL,
    content TEXT NOT NULL,
    status INTEGER NOT NULL,
    version TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER IF NOT EXISTS update_announcement_updated_at
AFTER UPDATE ON announcements
FOR EACH ROW
BEGIN
    UPDATE announcements SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""


class Announcement(Model):
    __tablename__ = "announcements"

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    type = fields.TextField(null=False)
    """公告类型"""
    content = fields.TextField(null=False)
    """公告内容"""
    status = fields.IntField(null=False)
    """公告状态"""
    version = fields.TextField(null=True)
    """版本"""
    created_at = fields.DatetimeField(auto_now_add=True)
    """创建时间"""
    updated_at = fields.DatetimeField(auto_now=True)
    """更新时间"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setup_database()

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "announcements"
        table_description = "公告表"

    async def setup_database(self):
        """
        连接到 SQLite 数据库并创建 announcements 表和触发器。
        """
        try:
            db = Tortoise.get_connection("default")
            await db.execute_script(CREATE_SQL)
            logger.info("表 'announcements' 创建成功或已存在。")

        except Exception as e:
            logger.error(f"数据库操作发生错误: {e}")

    @classmethod
    async def add_announcement(cls, type: str, content: str) -> int:
        """新增公告

        参数:
            公告类型
            公告内容

        返回:
            公告id
        """
        add = await cls.create(
            type=type,
            content=content,
            status=0,
        )
        return add.id

    # @classmethod
    # @dispatch('AnnouncementType', str)
    # async def add_announcement(cls, type: AnnouncementType, content: str) -> int:
    #     """新增公告
    #
    #     参数:
    #         公告类型
    #         公告内容
    #
    #     返回:
    #         公告id
    #     """
    #     add = await cls.create(
    #         type=type.value,
    #         content=content,
    #         status=0,
    #     )
    #     return add.id

    @classmethod
    async def get_announcement(cls, id: int):
        """获取公告

        参数:
            公告id

        返回:
            公告事项
        """
        try:
            announcement = await Announcement.get(id=id)
            return announcement
        except Exception:
            return None

    # @classmethod
    # @dispatch('Announcement')
    # async def get_announcement(cls, announcement: 'Announcement'):
    #     """获取公告
    #
    #     参数:
    #         公告id
    #
    #     返回:
    #         公告事项
    #     """
    #     return await cls.get_announcement(announcement.id)

    @classmethod
    async def delete_announcement(cls, id: int) -> bool:
        """删除公告

        参数:
            公告id

        返回:
            bool: 是否删除成功
        """
        if announcement := await cls.get_or_none(id=id):
            await announcement.delete()
            return True
        return False

    # @classmethod
    # @dispatch('Announcement')
    # async def delete_announcement(cls, announcement: 'Announcement') -> bool:
    #     """删除公告
    #
    #     参数:
    #         公告id
    #
    #     返回:
    #         bool: 是否删除成功
    #     """
    #     return await cls.delete_announcement(announcement.id)

    @classmethod
    async def update_announcement(cls, id: int, type: AnnouncementType | str | None = None, content: str | None = None,
                                  status: int | None = None, version: str | None = None) -> bool:
        """更新公告

        参数:
            公告id
            公告顺序
            公告内容
            公告状态
        """
        announcement = await cls.get_announcement(id=id)
        if announcement is not None:
            await cls.update_or_create(
                id=id,
                defaults={
                    "content": content or announcement.content,
                    "status": status or announcement.status,
                    "type": (type.value if isinstance(type, AnnouncementType) else type) or announcement.type,
                    "version": version or announcement.version,
                },
            )
            return True
        return False

    # @classmethod
    # @dispatch('Announcement')
    # async def update_announcement(cls, announcement: 'Announcement') -> bool:
    #     """更新公告
    #
    #     参数:
    #         Announcement实体
    #     """
    #     return await cls.update_announcement(announcement.id, announcement.type, announcement.content, announcement.status, announcement.version)

    @classmethod
    async def get_all_announcements(cls) -> list['Announcement']:
        """
        获得全部公告
        """
        return await cls.all()

    @classmethod
    async def get_announcements_with_type(cls, type: str | AnnouncementType) -> list['Announcement']:
        """
        获取某一类型的公告
        """
        query = await cls.all()
        announcement_lst = []
        for announcement in query:
            if announcement.type == (type.value if isinstance(type, AnnouncementType) else type):
                announcement_lst.append(announcement)
        return announcement_lst

    @classmethod
    async def get_post_announcements(cls) -> list['Announcement']:
        """
        获取已经发布的公告
        """
        query = await cls.all()
        announcement_lst = []
        for announcement in query:
            if announcement.status == 1:
                announcement_lst.append(announcement)
        return announcement_lst

    @classmethod
    async def get_unpost_announcements(cls) -> list['Announcement']:
        """
        获取没有发布的公告
        """
        query = await cls.all()
        announcement_lst = []
        for announcement in query:
            if announcement.status == 0:
                announcement_lst.append(announcement)
        return announcement_lst

    @classmethod
    async def post_announcement(cls, id: int) -> bool:
        """
        设置公告为已发布
        """
        announcement = await cls.get_announcement(id=id)
        if announcement is not None:
            await cls.update_or_create(
                id=id,
                defaults={
                    "status": 1,
                },
            )
            return True
        return False

    # @classmethod
    # @dispatch('Announcement')
    # async def post_announcement(cls, announcement: 'Announcement') -> bool:
    #     """
    #     设置公告为已发布
    #     """
    #     try:
    #         if not await cls.post_announcement(announcement.id):
    #             return False
    #     except Exception:
    #         return False
    #     return True

    @classmethod
    async def post_announcements(cls, list: list['Announcement']) -> bool:
        """
        设置公告为已发布
        """
        for announcement in list:
            try:
                if not await cls.post_announcement(announcement.id):
                    return False
            except Exception:
                return False
        return True
