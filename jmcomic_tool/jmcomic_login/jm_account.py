from tortoise import fields
from zhenxun.services.db_context import Model


class JmAccount(Model):
    # 自增id
    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    # 用户名
    username = fields.TextField(description="用户名")
    # 密码
    password = fields.TextField(description="密码")
    # QQ号
    qq_id = fields.TextField(description="QQ号")
    # 创建时间
    created_at = fields.DatetimeField(auto_now_add=True, description="创建时间")

    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "jm_account"
        table_description = "JM用户数据表"

    @classmethod
    async def get_user(cls, qq_id: str) -> "JmAccount":
        """获取用户

        参数:
            qq_id: 用户QQ号
        返回:
            JmAccount: JmAccount
        """
        if not await cls.exists(qq_id=qq_id):
            return JmAccount(id=-1)

        return await cls.get(qq_id=qq_id)

    @classmethod
    async def add_user(cls, username: str, password: str, qq_id: str) -> bool:
        """获取用户

        参数:
            username: 用户名
            password: 密码
            qq_id: 用户QQ号
        返回:
            bool: bool
        """
        if not await cls.exists(qq_id=qq_id):
            await cls.create(
                username=username,
                password=password,
                qq_id=qq_id,
            )
            return True
        else:
            return False

    @classmethod
    async def update_user(cls, username: str, password: str, qq_id: str) -> bool:
        """更新用户

        参数:
            username: 用户名
            password: 密码
            qq_id: 用户QQ号
        返回:
            bool: bool
        """
        if not await cls.exists(qq_id=qq_id):
            # 用户不存在
            return await cls.add_user(username=username, password=password, qq_id=qq_id)
        jm_account = await cls.get_user(qq_id=qq_id)
        jm_account.username = username
        jm_account.password = password
        try:
            await jm_account.save(update_fields=["username", "password"])
            return True
        except Exception as e:
            return False
