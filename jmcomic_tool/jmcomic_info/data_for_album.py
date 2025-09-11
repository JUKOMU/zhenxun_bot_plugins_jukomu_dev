from jmcomic import JmAlbumDetail


class DataForAlbum:
    def __init__(self):
        self.album: JmAlbumDetail | None = None  # 显式初始化

    def set_album(self, album: JmAlbumDetail):
        self.album = album

    def get_album(self) -> JmAlbumDetail:
        if self.album is None:
            raise ValueError("album 未初始化")
        return self.album
