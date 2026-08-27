import zlib
from urllib.parse import parse_qs, quote, unquote

import base62


def prune_magnet(magnet: str, display_name: str | None = None) -> str:
    """Reduce a magnet link to ``magnet:?xt=urn:btih:<hash>&dn=<quoted name>``.

    All ``&tr=`` trackers (and any other parameters) are stripped. The display
    name defaults to the decoded original ``dn``; passing ``display_name``
    overrides it. Returns the input unchanged when no btih info hash exists.
    """
    if not magnet.startswith("magnet:?"):
        return magnet
    params = parse_qs(magnet[len("magnet:?") :], keep_blank_values=True)
    xt = next(
        (v[0] for k, v in params.items() if k.lower() == "xt" and "urn:btih:" in v[0]),
        None,
    )
    if xt is None:
        return magnet
    name = display_name or unquote(params.get("dn", [""])[0])
    return f"magnet:?xt={xt}&dn={quote(name)}"


class Compress62:
    @staticmethod
    def compress(text: str) -> str:
        return base62.encodebytes(zlib.compress(text.encode()))

    @staticmethod
    def decompress(compressed: str) -> str:
        return zlib.decompress(base62.decodebytes(compressed)).decode()
