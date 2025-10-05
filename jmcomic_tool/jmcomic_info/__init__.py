import asyncio
import base64
import io
import os
import re
import time
from pathlib import Path

import PIL
import aiofiles
from PIL.Image import Image
from arclet.alconna import AllParam
from jmcomic import MissingAlbumPhotoException
from nonebot.adapters.onebot.v11 import Bot
from nonebot.plugin import PluginMetadata
from nonebot.rule import to_me
from nonebot_plugin_alconna import Alconna, Args, Arparma, on_alconna, UniMessage
from nonebot_plugin_uninfo import Uninfo

from zhenxun.configs.utils import PluginCdBlock, PluginExtraData
from zhenxun.services.log import logger
from zhenxun.utils.message import MessageUtils
from .data_for_album import DataForAlbum
from .data_source import JmDownload, cl, JmModuleConfig

__plugin_meta__ = PluginMetadata(
    name="Jm信息",
    description="懂的都懂，密码是id号",
    usage="""
    指令1：如果安装了Jm下载器则会同时下载本子
        jm [本子id]
    示例1：
        jm信息 114514
    指令2：
        jm信息 [本子id]
    示例2：
        jm信息 114514
    指令3：
        jm批量解析 [包含jm号的文本，jm号间需要有任意非数字字符隔开，支持换行，过滤长度小于3的jm号]
    示例3：
        jm批量解析 114514/113513 112512 
    """.strip(),
    extra=PluginExtraData(
        author="JUKOMU",
        version="1.0",
        menu_type="jmcomic",
        limits=[
            PluginCdBlock(result="Jm信息功能冷却中（5s）..."),
        ],
    ).to_dict(),
)

_matcher = on_alconna(
    Alconna("jm", Args["album_id", str]), priority=5, block=True, rule=to_me()
)

_info_matcher = on_alconna(
    Alconna("jm信息", Args["album_id", str]), priority=5, block=True, rule=to_me()
)

_mul_info_matcher = on_alconna(
    Alconna("jm批量解析", Args["album_id", AllParam]), priority=5, block=True, rule=to_me()
)


def generate_link_for_id(item_id):
    """
    根据给定的ID生成一个URL。
    """
    base_url = f'https://{cl.get_html_domain()}/album'
    return f"{base_url}/{item_id}"


def create_image_gallery_html(image_paths, descriptions_data, filename="photo_gallery_final_optimized.html"):
    """
    生成画廊html
    """
    if len(image_paths) != len(descriptions_data):
        raise ValueError("图片列表和描述列表的长度必须相同！")

    gallery_items_html = ""
    for img_path, desc_list in zip(image_paths, descriptions_data):
        item_id, title, line2, line3, line4 = desc_list
        link_url = generate_link_for_id(item_id)

        description_html = f"""
            <div class="item-description">
                <h4><a href="{link_url}" target="_blank">[{item_id}]</a>/{title}</h4>
                <p>作者: {line2}</p>
                <p>登场人物: {line3}</p>
                <p>标签: {line4}</p>
            </div>
        """

        gallery_items_html += f"""
        <div class="gallery-item">
            <img src="{img_path}" alt="{title}">
            {description_html}
        </div>
        """

    html_template = f"""
    <!DOCTYPE html>
    <html lang="zh-CN">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>JMComic Info</title>
        <style>
            body {{ 
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; 
                margin: 0; 
                padding: 0; /* 将内边距移至 main-content */
                background-color: #f0f2f5; 
            }}
    
            /* --- 核心改动 1: 添加主内容容器 --- */
            .main-content {{
                max-width: 1600px;   /* 设置内容区域的最大宽度，您可以根据喜好调整这个值 */
                margin: 0 auto;      /* 关键：当屏幕超过max-width时，使其水平居中 */
                padding: 20px;       /* 将原来的 body padding 移到这里 */
            }}
    
            h1 {{ text-align: center; color: #333; }}
            
            .controls-container {{
                text-align: center;
                margin-bottom: 20px;
            }}
            .controls-container label {{
                margin-right: 10px;
                color: #555;
                font-weight: bold;
            }}
            .controls-container select {{
                padding: 8px;
                border: 1px solid #ddd;
                border-radius: 5px;
                font-size: 1em;
                cursor: pointer;
            }}
    
            .gallery-container {{ 
                display: grid; 
                grid-template-columns: repeat(auto-fit, 280px); /* 恢复一个合理的默认宽度 */
                gap: 20px;
                justify-content: center;
            }}
    
            .gallery-item {{
                border: 1px solid #ddd; border-radius: 8px; overflow: hidden; background-color: #fff;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
                transition: transform 0.3s ease, box-shadow 0.3s ease;
                display: flex; flex-direction: column;
                width: 280px;
            }}
            
            .gallery-container.fixed-columns-mode .gallery-item {{
                width: auto;
            }}
            
            .gallery-item:hover {{ transform: translateY(-5px); box-shadow: 0 8px 16px rgba(0,0,0,0.2); }}
    
            .gallery-item img {{
                width: 100%; height: auto; display: block;
                aspect-ratio: 3 / 4;
                object-fit: cover;
            }}
    
            .item-description {{ padding: 15px; flex-grow: 1; display: flex; flex-direction: column; }}
            .item-description h4 {{ margin: 0 0 10px 0; font-size: 1.1em; color: #333; word-break: break-all; }}
            .item-description a {{ color: #007bff; text-decoration: none; font-weight: bold; }}
            .item-description a:hover {{ text-decoration: underline; }}
            .item-description p {{ margin: 0 0 5px 0; font-size: 0.9em; color: #666; line-height: 1.5; }}
    
            @media (max-width: 600px) {{
                .main-content {{
                    padding: 10px; /* 移动端使用更小的内边距 */
                }}
                h1 {{ font-size: 1.5em; }}
                .controls-container {{
                    display: none;
                }}
                .gallery-container {{
                    grid-template-columns: 1fr;
                    gap: 15px;
                }}
                .gallery-item {{ width: 100%; flex-direction: row; align-items: flex-start; }}
                .gallery-item img {{ width: 120px; flex-shrink: 0; }}
                .item-description {{ padding: 10px 15px; }}
            }}
        </style>
    </head>
    <body>
    
        <div class="main-content">
            <h1>图片画廊</h1>
            <div class="controls-container">
                <label for="columns-select">每行显示:</label>
                <select id="columns-select">
                    <option value="auto">自动</option>
                    <option value="2">2 个</option>
                    <option value="3">3 个</option>
                    <option value="4">4 个</option>
                    <option value="5" selected>5 个</option>
                    <option value="6">6 个</option>
                    <option value="7">7 个</option>
                    <option value="8">8 个</option>
                    <option value="9">9 个</option>
                    <option value="10">10 个</option>
                </select>
            </div>
            <div class="gallery-container">{gallery_items_html}</div>
        </div>
    </body>
    </html>
    """

    try:
        # Base64
        original_html_bytes = html_template.encode('utf-8')
        encoded_bytes = base64.b64encode(original_html_bytes)
        encoded_html_string = encoded_bytes.decode('utf-8')

        loader_html_to_write = f"""
        <!DOCTYPE html>
        <html lang="zh-CN">
        <head>
            <meta charset="UTF-8">
            <title>加载内容...</title>
            <style>
                body {{ display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; font-family: sans-serif; background-color: #f0f2f5; color: #888; }}
                .loader::after {{ content: '页面加载中，请稍候...'; }}
            </style>
        </head>
        <body>
            <div class="loader"></div>
            <script>
                (() => {{
                
                function initializeGalleryControls() {{
                    const selectElement = document.getElementById('columns-select');
                    const galleryContainer = document.querySelector('.gallery-container');

                    if (!selectElement || !galleryContainer) return;

                    function updateLayout(selectedValue) {{
                        if (selectedValue === 'auto') {{
                            // 恢复自动模式
                            galleryContainer.style.gridTemplateColumns = 'repeat(auto-fit, 280px)'; // 恢复默认值
                            galleryContainer.style.justifyContent = 'center';
                            galleryContainer.classList.remove('fixed-columns-mode');
                        }} else {{
                            // 切换到固定列模式
                            const columnCount = parseInt(selectedValue, 10);
                            galleryContainer.style.gridTemplateColumns = `repeat(${{columnCount}}, 1fr)`;
                            galleryContainer.style.justifyContent = 'initial';
                            galleryContainer.classList.add('fixed-columns-mode');
                        }}
                    }}

                    selectElement.addEventListener('change', (event) => {{
                        updateLayout(event.target.value);
                    }});

                    updateLayout(selectElement.value);
                    
                    function updateWidthDisplay() {{
                        const width = window.innerWidth;
                        
                        if (width <= 600) {{
                            // 恢复自动模式
                            galleryContainer.style.gridTemplateColumns = 'repeat(auto-fit, 280px)'; // 恢复默认值
                            galleryContainer.style.justifyContent = 'center';
                            galleryContainer.classList.remove('fixed-columns-mode');
                        }} else {{
                             // 切换到固定列模式
                            updateLayout(selectElement.value);
                        }}
                    }}

                    // 初始化
                    updateWidthDisplay();
                    
                    // 监听窗口大小变化
                    window.addEventListener('resize', updateWidthDisplay);

                }}
                
                    const encodedContent = `{encoded_html_string}`;

                    try {{
                        // 解码逻辑
                        const binaryString = atob(encodedContent);
                        const len = binaryString.length;
                        const bytes = new Uint8Array(len);
                        for (let i = 0; i < len; i++) {{
                            bytes[i] = binaryString.charCodeAt(i);
                        }}
                        const decoder = new TextDecoder('utf-8');
                        const decodedHtml = decoder.decode(bytes);
                        document.documentElement.innerHTML = decodedHtml;
                        initializeGalleryControls();
                    }} catch (e) {{
                        console.error("解码或渲染失败:", e);
                        document.body.innerHTML = "页面内容解码失败。";
                    }}
                }})();
            </script>
        </body>
        </html>"""

        current_timestamp = time.time()
        filepath = Path() / "resources" / "html" / "jmcomic" / f'{current_timestamp}.html'
        filename = filepath.absolute()
        if not filepath.exists():
            filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(loader_html_to_write)

        return current_timestamp

    except Exception as e:
        logger.error(f"生成文件时出错: {e}")


@_mul_info_matcher.handle()
async def __(bot: Bot, session: Uninfo, arparma: Arparma, album_id: UniMessage):
    await MessageUtils.build_message(f"正在解析中，请稍后...\n"
                                     f"本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev").send(
        reply_to=True)
    list = filter_duplicate_numbers(extract_numbers(album_id.extract_plain_text()))
    image_urls = []
    descriptions_structured = []
    for id in list:
        try:
            album = cl.get_album_detail(id)
        except Exception as e:
            continue
        # 构造其他标题名
        other_name = album.name.replace(album.oname, "")
        try:
            other_name_result = re.sub(r'\[.*?\]', '', other_name)
        except Exception as e:
            other_name_result = ''

        # 构造作者信息
        author_str = "["
        for i, value in enumerate(album.authors):
            if i == 0:
                author_str = author_str + value
            else:
                author_str = author_str + ", " + value
        author_str = author_str + "]"

        # 构造登场人物信息
        actor_str = "["
        for i, value in enumerate(album.actors):
            if i == 0:
                actor_str = actor_str + value
            else:
                actor_str = actor_str + ", " + value
        actor_str = actor_str + "]"

        # 构造标签信息
        tag_str = "["
        for i, value in enumerate(album.tags):
            if i == 0:
                tag_str = tag_str + value
            else:
                tag_str = tag_str + ", " + value
        tag_str = tag_str + "]"

        image_urls.append(f'https://{JmModuleConfig.DOMAIN_IMAGE_LIST[0]}/media/albums/{id}_3x4.jpg')
        descriptions_structured.append(
            [album.id, f'{album.authoroname}/{other_name_result.strip()}', author_str, actor_str, tag_str])
    current_timestamp = create_image_gallery_html(
        image_paths=image_urls,
        descriptions_data=descriptions_structured,
    )
    group_id = session.group.id if session.group else None
    filename = Path() / "resources" / "html" / "jmcomic" / f'{current_timestamp}.html'

    try:
        if group_id:
            await bot.call_api(
                "upload_group_file",
                group_id=group_id,
                file=f"file:///{filename.absolute()}",
                name=f"{current_timestamp}.html",
            )
        else:
            await bot.call_api(
                "upload_private_file",
                user_id=session.user.id,
                file=f"file:///{filename.absolute()}",
                name=f"{current_timestamp}.html",
            )
    except Exception as e:
        logger.error(
            "上传文件失败",
            "jmcomic",
            session=session.user.id,
            group_id=group_id,
            e=e,
        )


@_info_matcher.handle()
async def get_jm_info(bot: Bot, session: Uninfo, arparma: Arparma, album_id: str) -> UniMessage:
    group_id = session.group.id if session.group else None
    album_data = DataForAlbum()
    try:
        await JmDownload.download_avatar(bot, session.user.id, group_id, album_id, album_data)
    except MissingAlbumPhotoException as e:
        await MessageUtils.build_message(["本子不存在"]).send(
            reply_to=True)
    album = album_data.get_album()
    album_jpg = f"{album_id}.jpg"
    path = Path() / "resources" / "image" / "jmcomic" / album_jpg
    await compress_image(path.absolute())

    # 构造其他标题名
    other_name = album.name.replace(album.oname, "")
    other_name_result = re.sub(r'\[.*?\]', '', other_name)

    # 构造作者信息
    author_str = "["
    for i, value in enumerate(album.authors):
        if i == 0:
            author_str = author_str + value
        else:
            author_str = author_str + ", " + value
    author_str = author_str + "]"

    # 构造登场人物信息
    actor_str = "["
    for i, value in enumerate(album.actors):
        if i == 0:
            actor_str = actor_str + value
        else:
            actor_str = actor_str + ", " + value
    actor_str = actor_str + "]"

    # 构造标签信息
    tag_str = "["
    for i, value in enumerate(album.tags):
        if i == 0:
            tag_str = tag_str + value
        else:
            tag_str = tag_str + ", " + value
    tag_str = tag_str + "]"

    # 构造章节信息
    photo_id = ""
    photo_curr = ""
    photo_title = ""
    for i, value in enumerate(album.episode_list):
        # 章节编号
        photo_id = value[0]
        if photo_id == album_id:
            # 章节序号
            photo_curr = value[1]
            # 章节标题
            photo_title = value[2]
            break
    if photo_curr == "":
        photo_curr = 1
    photo_num = len(album.episode_list)
    # 总页数
    page_count = len(cl.get_photo_detail(album_id).page_arr)
    logger.info(f"本子信息 {album_id}", arparma.header_result, session=session)
    await MessageUtils.build_message([path,
                                      f'本子信息:\n'
                                      f'* [{album.id}]\n'
                                      f'* {album.authoroname}/{other_name_result.strip()}\n'
                                      f'* 作者: {author_str}\n'
                                      f'* 登场人物: {actor_str}\n'
                                      f'* tags: {tag_str}\n'
                                      f'* 章节标题: {photo_title}\n'
                                      f'* 页数: {page_count}\n'
                                      f'当前为第 {photo_curr} 章, 总章节数: {photo_num}\n'
                                      f'本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev']).send(
        reply_to=True)


@_matcher.handle()
async def get_jm_info(bot: Bot, session: Uninfo, arparma: Arparma, album_id: str) -> UniMessage | None:
    group_id = session.group.id if session.group else None
    album_data = DataForAlbum()
    try:
        await JmDownload.download_avatar(bot, session.user.id, group_id, album_id, album_data)
    except MissingAlbumPhotoException as e:
        return
    album = album_data.get_album()
    album_jpg = f"{album_id}.jpg"
    path = Path() / "resources" / "image" / "jmcomic" / album_jpg
    await compress_image(path.absolute())

    # 构造其他标题名
    other_name = album.name.replace(album.oname, "")
    other_name_result = re.sub(r'\[.*?\]', '', other_name)

    # 构造作者信息
    author_str = "["
    for i, value in enumerate(album.authors):
        if i == 0:
            author_str = author_str + value
        else:
            author_str = author_str + ", " + value
    author_str = author_str + "]"

    # 构造登场人物信息
    actor_str = "["
    for i, value in enumerate(album.actors):
        if i == 0:
            actor_str = actor_str + value
        else:
            actor_str = actor_str + ", " + value
    actor_str = actor_str + "]"

    # 构造标签信息
    tag_str = "["
    for i, value in enumerate(album.tags):
        if i == 0:
            tag_str = tag_str + value
        else:
            tag_str = tag_str + ", " + value
    tag_str = tag_str + "]"

    # 构造章节信息
    photo_id = ""
    photo_curr = ""
    photo_title = ""
    for i, value in enumerate(album.episode_list):
        # 章节编号
        photo_id = value[0]
        if photo_id == album_id:
            # 章节序号
            photo_curr = value[1]
            # 章节标题
            photo_title = value[2]
            break
    if photo_curr == "":
        photo_curr = 1
    photo_num = len(album.episode_list)
    # 总页数
    page_count = len(cl.get_photo_detail(album_id).page_arr)
    logger.info(f"本子信息 {album_id}", arparma.header_result, session=session)
    await MessageUtils.build_message([path,
                                      f'本子信息:\n'
                                      f'* [{album.id}]\n'
                                      f'* {album.authoroname}/{other_name_result.strip()}\n'
                                      f'* 作者: {author_str}\n'
                                      f'* 登场人物: {actor_str}\n'
                                      f'* tags: {tag_str}\n'
                                      f'* 章节标题: {photo_title}\n'
                                      f'* 页数: {page_count}\n'
                                      f'当前为第 {photo_curr} 章, 总章节数: {photo_num}\n'
                                      f'本插件及其相关已在GitHub开源, 详见: https://github.com/JUKOMU/zhenxun_bot_plugins_jukomu_dev']).send(
        reply_to=True)


async def compress_image(image_path, target_kb=500, quality=95):
    """
    异步压缩指定路径的图片，使得压缩后文件大小不超过 target_kb KB，
    如果原文件小于目标大小则不做操作。压缩过程中保持原比例缩放，并尽可能保证图片质量。
    最后将处理后的图片覆盖原文件。
    """
    target_size = target_kb * 1024  # 目标大小（字节）

    # 异步检查原图片大小
    file_size = await asyncio.to_thread(os.path.getsize, image_path)
    if file_size <= target_size:
        logger.info("原图片已小于目标大小，无需处理。")
        return

    # 异步打开图片
    img = await asyncio.to_thread(PIL.Image.open, image_path)
    width, height = img.size

    low, high = 0.1, 1.0
    best_data = None

    for _ in range(20):  # 迭代 20 次，通常足够找到合适比例
        mid = (low + high) / 2
        new_width = int(width * mid)
        new_height = int(height * mid)
        # 异步按比例缩放图片（放到线程中执行）
        img_resized = await asyncio.to_thread(img.resize, (new_width, new_height))

        # 保存到内存中检查文件大小
        buffer = io.BytesIO()
        await asyncio.to_thread(img_resized.save, buffer, format=img.format, quality=quality, optimize=True)
        data = buffer.getvalue()
        size = len(data)

        # 如果压缩后小于目标，则记录数据，并尝试放大图片以保持较高质量
        if size <= target_size:
            best_data = data
            low = mid  # 尝试更大尺寸
        else:
            high = mid  # 需要缩小

    if best_data:
        # 异步写回原文件
        async with aiofiles.open(image_path, 'wb') as f:
            await f.write(best_data)
        logger.info("图片压缩成功，已覆盖原文件。")
    else:
        logger.info("无法将图片压缩到目标大小。")


def extract_numbers(text) -> list[str]:
    """
    提取字符串中的连续数字串并过滤长度小于3的数字串
    """
    # 使用正则表达式匹配所有连续数字
    numbers = re.findall(r'\d+', text)
    # 过滤掉长度为1的数字串
    filtered = [num for num in numbers if len(num) > 3]
    return filtered


def filter_duplicate_numbers(number_list):
    """
    过滤连续数字串列表中的重复项
    """
    seen = set()
    unique_numbers = []
    for num in number_list:
        if num not in seen:
            seen.add(num)
            unique_numbers.append(num)
    return unique_numbers
