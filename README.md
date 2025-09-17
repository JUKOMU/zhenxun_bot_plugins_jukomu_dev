<p align="center">
  <a href="./README.zh.md">中文</a>
  <span>&nbsp;</span>
  <strong>English</strong>
</p>

# JUKOMU’s Zhenxun Bot Plugins (JMComic & Pixiv Extensions)

This is a plugin collection for [Zhenxun Bot (zhenxun-bot)](https://github.com/zhenxun-org/zhenxun_bot) based on NoneBot2. It mainly adds features related to JMComic and Pixiv.

## Upstream Project

[![Readme Card](https://github-readme-stats.vercel.app/api/pin/?username=zhenxun-org&repo=zhenxun_bot)](https://github.com/zhenxun-org/zhenxun_bot)
[![Readme Card](https://github-readme-stats.vercel.app/api/pin/?username=hect0x7&repo=JMComic-Crawler-Python)]([https://github.com/zhenxun-org/zhenxun_bot](https://github.com/hect0x7/JMComic-Crawler-Python))

## Feature Overview

- JMComic Tool
  - [View work information](./jmcomic_tool/jmcomic_info/__init__.py)
  - [View chapter information](./jmcomic_tool/jmcomic_photo_info/__init__.py)
  - [Download work](./jmcomic_tool/jmcomic_downloader/__init__.py)
  - [Search works](./jmcomic_tool/jmcomic_search/__init__.py)
  - [JM login](./jmcomic_tool/jmcomic_login/__init__.py)
  - [View JM favorites](./jmcomic_tool/jmcomic_favourite/__init__.py)

- Pixiv
  - [Get illustration by illustration ID](./pivix_tool/__init__.py)
  - [Get illustration info by illustration ID](./pivix_tool/__init__.py)
  - [Get author info by author ID](./pivix_tool/__init__.py)
  - [Get author works by author ID](./pivix_tool/__init__.py)

> The actual available features depend on which plugins from this repository you enable. Use the bot’s built-in help to see the commands exposed by your instance.

## Compatibility

- Recommended environment: Follow your zhenxun-bot runtime environment.

## Configuration

- Pixiv requires a proxy server.
- Pixiv refresh tokens can be obtained via common Pixiv API login flows. Always comply with Pixiv’s terms and policies.

## Notes

- Network: Accessing Pixiv and JMComic may require a proxy or mirror in some regions.
- Content compliance: Enable content filtering or restrictions per community guidelines and local laws.

## Contributing

Issues and PRs are welcome. Please include your runtime environment, reproduction steps, and error logs (if any). It’s recommended to follow the styles and conventions of the zhenxun-bot/NoneBot2 ecosystem.

## License

See the LICENSE file in this repository. Ensure compliance with the upstream project and the terms of any API providers during use.
