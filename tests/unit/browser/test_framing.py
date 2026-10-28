"""Chrome's native messaging framing, both ways."""
import io
import struct

import pytest

from marginalia.browser.framing import MAX_TO_CHROME, FramingError, read_message, write_message


def framed(body: bytes) -> bytes:
    return struct.pack("=I", len(body)) + body


def test_round_trip_keeps_unicode():
    out = io.BytesIO()
    write_message(out, {"text": "ψ ⟨0|1⟩"})
    assert read_message(io.BytesIO(out.getvalue())) == {"text": "ψ ⟨0|1⟩"}


def test_a_closed_pipe_is_the_end():
    assert read_message(io.BytesIO(b"")) is None


@pytest.mark.parametrize(
    "data",
    [b"\x05\x00", framed(b'{"a":')[:-2], framed(b"not json"), struct.pack("=I", 2**31) + b"{}"],
    ids=["short length", "short body", "not json", "too large"],
)
def test_malformed_input_is_an_error_not_a_crash(data):
    with pytest.raises(FramingError):
        read_message(io.BytesIO(data))


def test_refuses_a_reply_chrome_would_drop():
    with pytest.raises(FramingError):
        write_message(io.BytesIO(), {"x": "a" * MAX_TO_CHROME})
