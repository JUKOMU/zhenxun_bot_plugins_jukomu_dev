from enum import Enum
from typing import Any, Coroutine

from tortoise import Tortoise
from tortoise import fields
from zhenxun.services.db_context import Model
from zhenxun.services.log import logger
from multipledispatch import dispatch


class TodoStatus(Enum):
    """
    待办事项的状态枚举。
    - value: 存储在数据库中的值。
    - description: 用于显示的描述文本。
    """
    PENDING = 'pending'
    COMPLETED = 'completed'
    PAUSED = 'paused'

    @classmethod
    def description(cls, status: str) -> str:
        """
        获取状态的中文描述。
        """
        if status == TodoStatus.PENDING:
            return "待处理"
        elif status == TodoStatus.COMPLETED:
            return "已完成"
        elif status == TodoStatus.PAUSED:
            return "已暂停"
        else:
            return "未知状态"


CREATE_SQL = """
CREATE TABLE IF NOT EXISTS todos
(
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    "index" INTEGER NOT NULL,
    content TEXT NOT NULL,
    status TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE TRIGGER IF NOT EXISTS update_todos_updated_at
AFTER UPDATE ON todos
FOR EACH ROW
BEGIN
    UPDATE todos SET updated_at = CURRENT_TIMESTAMP WHERE id = OLD.id;
END;
"""


class Todo(Model):
    __tablename__ = "todos"

    id = fields.IntField(pk=True, generated=True, auto_increment=True)
    """自增id"""
    index = fields.IntField(null=False)
    """事项顺序"""
    content = fields.TextField(null=False)
    """事项内容"""
    status = fields.TextField(null=False)
    """事项状态"""
    created_at = fields.DatetimeField(auto_now_add=True)
    """创建时间"""
    updated_at = fields.DatetimeField(auto_now=True)

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setup_database()


    class Meta:  # pyright: ignore [reportIncompatibleVariableOverride]
        table = "todos"
        table_description = "待办事项列表"

    async def setup_database(self):
        """
        连接到 SQLite 数据库并创建 todos 表和触发器。
        """
        try:
            db = Tortoise.get_connection("default")
            await db.execute_script(CREATE_SQL)
            logger.info("表 'todos' 创建成功或已存在。")

        except Exception as e:
            logger.error(f"数据库操作发生错误: {e}")

    @classmethod
    async def add_todo(cls, content: str) -> int:
        """新增待办

        参数:
            待办内容

        返回:
            待办id
        """
        index: int = len(await cls.get_all_pending_todos()) + 1
        add = await cls.create(
            index=index,
            content=content,
            status=TodoStatus.PENDING,
        )
        return add.id

    @classmethod
    @dispatch(int)
    async def get_todo(cls, id: int):
        """获取待办

        参数:
            待办id

        返回:
            待办事项
        """
        try:
            todo = await Todo.get(id=id)
            return todo
        except Exception:
            return None

    @classmethod
    @dispatch('Todo')
    async def get_todo(cls, todo: 'Todo'):
        """获取待办

        参数:
            待办id

        返回:
            待办事项
        """
        return await cls.get_todo(todo.id)

    @classmethod
    @dispatch(int)
    async def delete_todo(cls, id: int) -> bool:
        """删除待办

        参数:
            待办id

        返回:
            bool: 是否删除成功
        """
        if todo := await cls.get_or_none(id=id):
            await todo.delete()
            return True
        return False

    @classmethod
    @dispatch('Todo')
    async def delete_todo(cls, todo: 'Todo') -> bool:
        """删除待办

        参数:
            待办id

        返回:
            bool: 是否删除成功
        """
        return await cls.delete_todo(todo.id)

    @classmethod
    @dispatch(int, int, str, str)
    async def update_todo(cls, id: int, index: int | None = None, content: str | None = None,
                          status: str | None = None) -> bool:
        """更新待办

        参数:
            待办id
            待办顺序
            待办内容
            待办状态
        """
        todo = await cls.get_todo(id=id)
        if todo is not None:
            await cls.update_or_create(
                id=id,
                defaults={
                    "content": content or todo.content,
                    "status": status or todo.status,
                    "index": index or todo.index,
                },
            )
            pending_list = await cls.get_all_pending_todos()
            for i in range(1, len(pending_list)+1):
                if len(pending_list) == 1:
                    await cls.update_todo(pending_list[0].id, i)
                min = None
                min_index = 99999999
                # 查找最小
                for p in pending_list:
                    if len(pending_list) == 1:
                        min = p
                        break
                    if p.id > 0 and p.id < min_index:
                        min = p
                        min_index = p.id
                min.index = i
                await cls.update_todo(min)
            return True
        return False

    @classmethod
    @dispatch('Todo')
    async def update_todo(cls, todo: 'Todo') -> bool:
        """更新待办

        参数:
            Todo实体
        """
        return await cls.update_todo(todo.id, todo.index, todo.content, todo.status)

    @classmethod
    async def get_all_todos(cls) -> list['Todo']:
        """
        获得全部待办
        """
        return await cls.all()

    @classmethod
    async def get_all_pending_todos(cls) -> list['Todo']:
        """
        获得全部进行中待办
        """
        query = await cls.all()
        todo_lst = []
        for todo in query:
            if todo.status == TodoStatus.PENDING:
                todo_lst.append(todo)
        return todo_lst

    @classmethod
    async def get_all_completed_todos(cls) -> list['Todo']:
        """
        获得全部完成待办
        """
        query = await cls.all()
        todo_lst = []
        for todo in query:
            if todo.status == TodoStatus.COMPLETED:
                todo_lst.append(todo)
        return todo_lst

    @classmethod
    async def get_all_paused_todos(cls) -> list['Todo']:
        """
        获得全部暂停待办
        """
        query = await cls.all()
        todo_lst = []
        for todo in query:
            if todo.status == TodoStatus.PAUSED:
                todo_lst.append(todo)
        return todo_lst

    @classmethod
    @dispatch('Todo')
    async def finish(cls, todo: 'Todo') -> bool:
        todo.status = str(TodoStatus.COMPLETED)
        todo.index = -1
        return await cls.update_todo(todo)

    @classmethod
    @dispatch(int)
    async def finish(cls, id: int):
        return await cls.update_todo(id=id, index=-1, status=str(TodoStatus.COMPLETED))

    @classmethod
    @dispatch('Todo')
    async def paused(cls, todo: 'Todo') -> bool:
        todo.status = str(TodoStatus.PAUSED)
        todo.index = 0
        return await cls.update_todo(todo)

    @classmethod
    @dispatch(int)
    async def paused(cls, id: int):
        return await cls.update_todo(id=id, index=0, status=str(TodoStatus.PAUSED))

    @classmethod
    @dispatch('Todo')
    async def pending(cls, todo: 'Todo') -> bool:
        todo.status = str(TodoStatus.PENDING)
        return await cls.update_todo(todo)

    @classmethod
    @dispatch(int)
    async def pending(cls, id: int):
        return await cls.update_todo(id=id, status=str(TodoStatus.PENDING))

    @classmethod
    async def change_index(cls, id: int, index: int) -> bool:
        try:
            todo1 = await cls.get_todo(id=id)
            todo2 = await cls.get(index=index)
            todo2.index = todo1.index
            todo1.index = index
            await cls.update_or_create(
                id=todo1.id,
                defaults={
                    "index": todo1.index,
                }, )

            await cls.update_or_create(
                id=todo2.id,
                defaults={
                    "index": todo2.index,
                }, )
            return True
        except Exception:
            return False


