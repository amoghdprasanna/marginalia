"""Chrome's native messaging framing: a 4-byte length in native byte order, then UTF-8 JSON.

https://developer.chrome.com/docs/extensions/develop/concepts/native-messaging
"""
from __future__ import annotations

import json
import struct
from typing import Any, BinaryIO

# Chrome refuses a message from the helper larger than 1 MB; messages to it may be bigger.
MAX_TO_CHROME = 1024 * 1024
MAX_FROM_CHROME = 64 * 1024 * 1024
_LENGTH = struct.Struct("=I")  # native byte order, as Chrome writes it


class FramingError(Exception):
    """The stream from Chrome is not a well-formed message."""


def read_message(stream: BinaryIO) -> Any | None:
    """The next message, or None when Chrome closed the pipe (the panel went away)."""
    header = stream.read(_LENGTH.size)
    if not header:
        return None
    if len(header) < _LENGTH.size:
        raise FramingError("the message length was cut short")
    (length,) = _LENGTH.unpack(header)
    if length > MAX_FROM_CHROME:
        raise FramingError(f"a {length}-byte message is larger than {MAX_FROM_CHROME}")
    body = stream.read(length)
    if len(body) < length:
        raise FramingError("the message was cut short")
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FramingError(f"the message is not JSON: {exc}") from exc


def write_message(stream: BinaryIO, message: Any) -> None:
    body = json.dumps(message, ensure_ascii=False).encode("utf-8")
    if len(body) > MAX_TO_CHROME:
        raise FramingError(f"a {len(body)}-byte reply is larger than Chrome accepts")
    stream.write(_LENGTH.pack(len(body)) + body)
    stream.flush()
