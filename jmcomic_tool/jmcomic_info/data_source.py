import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import jmcomic
from jmcomic import JmAlbumDetail, JmModuleConfig
from nonebot.adapters.onebot.v11 import Bot
from zhenxun.configs.path_config import DATA_PATH

from .data_for_album import DataForAlbum

JPG_OUTPUT_PATH = "/resources/image/jmcomic"
PDF_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_pdf"
ZIP_OUTPUT_PATH = DATA_PATH / "jmcomic" / "jmcomic_zip"
PDF_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)
ZIP_OUTPUT_PATH.mkdir(parents=True, exist_ok=True)

OPTION_FILE = Path(__file__).parent / "option.yml"

op = jmcomic.create_option_by_file(str(OPTION_FILE.absolute()))

cl = op.new_jm_client()


@dataclass
class DetailInfo:
    bot: Bot
    user_id: str
    group_id: str | None
    album_id: str


class JmDownload:
    _data: ClassVar[dict[str, list[DetailInfo]]] = {}
    album_data: DataForAlbum = DataForAlbum()

    @classmethod
    async def upload_file(cls, data: DetailInfo):
        return cls.album_data

    @classmethod
    def call_send(cls, album: JmAlbumDetail, dler):
        cls.album_data.set_album(album)

        data_list = cls._data.get(album.id)
        if not data_list:
            return
        try:
            loop = asyncio.get_running_loop()
        except Exception:
            loop = None
        for data in data_list:
            if loop:
                pass
                # loop.create_task(cls.upload_file(data))
            else:
                pass
                # asyncio.run(cls.upload_file(data))
        del cls._data[album.id]

    @classmethod
    async def download_avatar(
            cls, bot: Bot, user_id: str, group_id: str | None, album_id: str, album_data: DataForAlbum
    ):
        """
        下载封面
        """

        url = f'https://{JmModuleConfig.DOMAIN_IMAGE_LIST[0]}/media/albums/{album_id}_3x4.jpg'

        cls.album_data = album_data

        if album_id not in cls._data:
            cls._data[album_id] = []
        cls._data[album_id].append(
            DetailInfo(
                bot=bot, user_id=user_id, group_id=group_id, album_id=album_id
            )
        )

        detail = cl.get_album_detail(album_id)
        album_data.set_album(detail)
        filepath = Path() / "resources" / "image" / "jmcomic" / f"{album_id}.jpg"
        cover_path = filepath.absolute()
        if not Path(cover_path).exists():
            await asyncio.to_thread(
                cl.download_image, url, cover_path, decode_image=False
            )
