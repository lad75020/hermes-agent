"""Embedded images are attached as files and hidden from streaming display."""

import base64
import json

from gateway.platforms.base import BasePlatformAdapter
from gateway.stream_consumer import GatewayStreamConsumer


class TestExtractBase64Images:
    def test_image_base64_json_saved_and_redacted(self, tmp_path, monkeypatch):
        raw_png = b"\x89PNG\r\n\x1a\n" + b"fake-png-bytes"
        b64 = base64.b64encode(raw_png).decode("ascii")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        payload = json.dumps({
            "type": "generated_image",
            "mime_type": "image/png",
            "filename": "sample.png",
            "image_base64": b64,
        })

        paths, cleaned = BasePlatformAdapter.extract_base64_images(payload)

        assert len(paths) == 1
        assert paths[0].endswith("sample.png")
        with open(paths[0], "rb") as f:
            assert f.read() == raw_png
        assert b64 not in cleaned
        assert "[omitted; sent as image attachment]" in cleaned

    def test_data_image_url_saved_and_redacted(self, tmp_path, monkeypatch):
        raw_jpeg = b"\xff\xd8\xff" + b"fake-jpeg-bytes"
        b64 = base64.b64encode(raw_jpeg).decode("ascii")
        monkeypatch.setenv("HERMES_HOME", str(tmp_path))
        content = f"Here: ![x](data:image/jpeg;base64,{b64})"

        paths, cleaned = BasePlatformAdapter.extract_base64_images(content)

        assert len(paths) == 1
        assert paths[0].endswith(".jpg")
        with open(paths[0], "rb") as f:
            assert f.read() == raw_jpeg
        assert b64 not in cleaned
        assert "data:image/jpeg;base64,[omitted; sent as image attachment]" in cleaned


class TestBase64StreamDisplay:
    def test_image_base64_payload_redacted(self):
        """Streaming must not push megabytes of image_base64 text to chat APIs."""
        b64 = "A" * 5000
        text = f'{{"mime_type":"image/png","image_base64":"{b64}"}}'
        result = GatewayStreamConsumer._clean_for_display(text)
        assert b64 not in result
        assert "[omitted; sent as image attachment]" in result

    def test_data_image_url_payload_redacted(self):
        b64 = "A" * 5000
        text = f"![image](data:image/png;base64,{b64})"
        result = GatewayStreamConsumer._clean_for_display(text)
        assert b64 not in result
        assert "data:image/png;base64,[omitted; sent as image attachment]" in result
