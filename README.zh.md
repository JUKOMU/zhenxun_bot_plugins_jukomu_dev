# JUKOMU 的真寻 Bot 插件（JMComic & Pixiv 扩展）

这是一个为 [真寻 Bot（zhenxun-bot）](https://github.com/zhenxun-org/zhenxun_bot) 开发的插件集合（基于 NoneBot2），主要新增了与 JMComic 和 Pixiv 相关的功能，用于增强媒体检索、搜索与内容推送能力。


## 上游项目：

  [![Readme Card](https://github-readme-stats.vercel.app/api/pin/?username=zhenxun-org&repo=zhenxun_bot)](https://github.com/zhenxun-org/zhenxun_bot)

## 功能概览

- JMComic Tool
  - [查看本子信息](./jmcomic_tool/jmcomic_info/__init__.py)
  - [查看章节信息](./jmcomic_tool/jmcomic_photo_info/__init__.py)
  - [下载本子](./jmcomic_tool/jmcomic_downloader/__init__.py)
  - [搜索本子](./jmcomic_tool/jmcomic_search/__init__.py)
  - [jm登录](./jmcomic_tool/jmcomic_login/__init__.py)
  - [查看jm收藏夹](./jmcomic_tool/jmcomic_favourite/__init__.py)

- Pixiv
  - [根据插画id获取作品](./pivix_tool/__init__.py)
  - [根据插画id获取作品信息](./pivix_tool/__init__.py)
  - [根据作者id获取作者信息](./pivix_tool/__init__.py)
  - [根据作者id获取作者作品](./pivix_tool/__init__.py)


> 具体可用功能以您启用的本仓库内插件为准。请使用机器人自带的帮助功能查看该实例实际暴露的指令。

## 兼容性
- 建议环境：以您的zhenxun-bot 运行环境为准

[//]: # (## 安装方式)

[//]: # ()
[//]: # (将本仓库作为本地插件引入到已有的真寻 Bot 实例中。)

[//]: # ()
[//]: # (方式 A — 将仓库路径加入本地插件目录：)

[//]: # (1. 克隆本仓库：)

[//]: # (   ```bash)

[//]: # (   git clone https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev.git)

[//]: # (   ```)

[//]: # (2. 在您的真寻 Bot 项目中，将该仓库的绝对路径加入本地插件检索路径。)

[//]: # (   - 如果使用 `.env` 或 `.env.*` 配置，可新增本地插件目录项（键名需与您的项目/加载器对应），例如：)

[//]: # (     ```)

[//]: # (     # 仅为示例 — 请根据项目实际配置键名调整)

[//]: # (     PLUGIN_DIRS=/absolute/path/to/zhenxun_bot_plugins_jukomu_dev)

[//]: # (     ```)

[//]: # (   - 或者在 NoneBot 配置中设置 `plugin_dirs`，包含此路径。)

[//]: # (3. 重启机器人，使用帮助命令确认插件是否成功加载。)

[//]: # ()
[//]: # (方式 B — 拷贝所需插件目录：)

[//]: # (1. 克隆本仓库。)

[//]: # (2. 将需要的插件子目录拷贝到您的真寻 Bot 本地插件目录（即机器人用于自动发现本地插件的目录）。)

[//]: # (3. 重启机器人。)

[//]: # ()
[//]: # (> 插件目录结构可能有所差异。通常每个子目录即代表一个插件包/模块。如需显式启用，请在配置的 `plugins` 列表中添加对应插件名。)

## 配置说明

- Pixiv 需要配置代理服务器
- Pixiv 的刷新 Token 可通过常见的 Pixiv API 登录流程获取；务必遵守 Pixiv 平台条款与政策。

## 注意事项

- 网络：在部分地区访问 Pixiv、JMComic 可能需要代理或镜像。
- 内容合规：请根据社区规范与当地法律开启内容过滤或限制功能。

## 参与贡献

欢迎提交 Issue 与 PR。请尽量提供运行环境、复现步骤与错误日志（如有）。建议遵循 zhenxun-bot/NoneBot2 生态的风格与规范。

## 许可协议

请参阅仓库内的 LICENSE 文件。使用过程中请确保遵守上游项目与各 API 提供方的使用条款。