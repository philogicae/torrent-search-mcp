import re
import zlib
from urllib.parse import parse_qs, quote, unquote

import base62

# Torrent ids embed a zlib-compressed query. A crafted id could otherwise be a
# decompression bomb, so decompression is capped to the longest query we accept
# anywhere in the stack (API, MCP and ids).
MAX_QUERY_BYTES = 4096

_BTIH = re.compile(r"urn:btih:(?:[0-9a-fA-F]{40}|[A-Za-z2-7]{32})\Z", re.IGNORECASE)


def prune_magnet(magnet: str, display_name: str | None = None) -> str:
    """Reduce a magnet link to ``magnet:?xt=urn:btih:<hash>&dn=<quoted name>``.

    All ``&tr=`` trackers (and any other parameters) are stripped. The display
    name defaults to the decoded original ``dn``; passing ``display_name``
    overrides it. Returns the input unchanged when no valid btih info hash
    exists. The info hash is validated so a crafted ``xt`` value cannot smuggle
    extra magnet parameters (e.g. a tracker) through percent-decoding.
    """
    if not magnet.lower().startswith("magnet:?"):
        return magnet
    params = parse_qs(magnet[len("magnet:?") :], keep_blank_values=True)
    xt = next(
        (
            values[0]
            for key, values in params.items()
            if key.lower() == "xt" and _BTIH.fullmatch(values[0])
        ),
        None,
    )
    if xt is None:
        return magnet
    dn = next(
        (values[0] for key, values in params.items() if key.lower() == "dn"),
        "",
    )
    name = display_name or unquote(dn)
    return f"magnet:?xt={xt}&dn={quote(name)}"


class Compress62:
    @staticmethod
    def compress(text: str) -> str:
        return base62.encodebytes(zlib.compress(text.encode()))

    @staticmethod
    def decompress(compressed: str) -> str:
        payload = base62.decodebytes(compressed)
        inflater = zlib.decompressobj()
        data = inflater.decompress(payload, MAX_QUERY_BYTES + 1)
        if len(data) > MAX_QUERY_BYTES or inflater.unconsumed_tail:
            raise ValueError("compressed query exceeds the size limit")
        data += inflater.flush()
        return data.decode()
