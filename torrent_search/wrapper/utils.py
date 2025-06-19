import zlib

import base62


class Compress62:
    @staticmethod
    def compress(text: str) -> str:
        return base62.encodebytes(zlib.compress(text.encode()))  # type: ignore

    @staticmethod
    def decompress(compressed: str) -> str:
        return zlib.decompress(base62.decodebytes(compressed)).decode()  # type: ignore
