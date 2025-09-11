## 使用

### zhenxun bot数据库建表

```sql
CREATE TABLE jm_account (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    qq_id TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT jm_account_unique_username UNIQUE (username)
);

-- 表注释
COMMENT ON TABLE jm_account IS 'JM用户数据表';
        
-- 字段注释
/*
字段说明：
- id: 自增主键
- username: 用户名
- password: 密码
- qq_id: QQ号
- created_at: 创建时间（自动记录插入时间）
*/

```

### 将jm_account.py放入models文件夹

```
    zhenxun_bot
    |----zhenxun
         |----models
```