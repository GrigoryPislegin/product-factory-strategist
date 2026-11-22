import contextlib
import http.client
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from xml.etree import ElementTree as ET
from zipfile import ZipFile

import run_api


class LocalAPITests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.source = self.path / "brief.md"
        self.source.write_text("Проект\nВ очереди 42 семьи.\n", encoding="utf-8")
        self.private = self.path / "private.txt"
        self.private.write_text("UNLISTED-DOCUMENT", encoding="utf-8")
        self.folder = self.path / "case"
        self.requests = []
        self.replies = []
        case = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                case.requests.append((self.path, self.headers.get("Authorization"), json.loads(body)))
                status, data = case.replies.pop(0)
                content = json.dumps(data).encode()
                self.send_response(status)
                self.send_header("Content-Length", str(len(content)))
                self.end_headers()
                self.wfile.write(content)

            def log_message(self, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        transport = patch.object(run_api.http.client, "HTTPSConnection",
                                 side_effect=lambda host, timeout: http.client.HTTPConnection(
                                     *server.server_address, timeout=timeout))
        transport.start()
        self.addCleanup(transport.stop)
        env = patch.dict(os.environ, {"OPENAI_API_KEY": "dummy-key-for-local-http"})
        env.start()
        self.addCleanup(env.stop)
        self.new = ["new", str(self.folder), "--file", str(self.source), "--question", "Что выбрать?"]
        self.resume = ["resume", str(self.folder)]
        self.choose = self.resume + ["--choose", "1", "--reason", "Проверить спрос"]
        self.research = {"evidence": [{"source": "S1", "quote": "42 семьи", "finding": "Размер очереди"}],
                         "options": [{"kind": kind, "title": kind, "benefit": "Польза", "objection": "Риск"}
                                     for kind in ("change", "status_quo", "close")], "gaps": ["Цена пилота"]}
        self.strategy = {k: "Проверяем на согласованной группе" for k in
                         ("product", "communication", "measurement", "next_step")}

    def invoke(self, args):
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            code = run_api.main(args)
        self.assertNotIn("dummy-key-for-local-http", output.getvalue())
        return code, output.getvalue()

    def reply(self, data):
        self.replies.append((200, {"status": "completed", "output": [{"type": "message", "content": [
            {"type": "output_text", "text": json.dumps(data, ensure_ascii=False)}]}]}))

    def test_new_choice_restart_and_offline_resume(self):
        self.reply(self.research)
        self.assertEqual(self.invoke(self.new)[0], 0)
        self.assertFalse((self.folder / "strategy.md").exists())
        self.assertFalse((self.folder / "strategy.pptx").exists())
        self.assertIn("brief.md, строка 2", (self.folder / "comparison.md").read_text())
        self.assertEqual(self.invoke(self.resume)[0], 0)
        self.assertEqual(self.invoke(self.resume + ["--choose", "99", "--reason", "выбор"])[0], 1)
        self.assertEqual(len(self.requests), 1)
        self.replies.append((429, {"error": "ignored"}))
        self.assertEqual(self.invoke(self.choose)[0], 1)
        self.source.unlink()
        self.reply(self.strategy)
        self.assertEqual(self.invoke(self.resume)[0], 0)
        pptx = self.folder / "strategy.pptx"
        original = pptx.read_bytes()
        with ZipFile(pptx) as deck:
            presentation = ET.fromstring(deck.read("ppt/presentation.xml"))
            self.assertEqual(len(presentation.findall(".//{*}sldId")), 6)
            size = presentation.find("{*}sldSz")
            self.assertGreater(int(size.get("cx")), int(size.get("cy")))
            for n, expected in enumerate(("Проверить спрос", "status_quo", "42 семьи",
                                          self.strategy["product"], self.strategy["communication"],
                                          self.strategy["next_step"]), 1):
                slide = ET.fromstring(deck.read(f"ppt/slides/slide{n}.xml"))
                text = " ".join(t.text or "" for t in slide.findall(".//{*}sp/{*}txBody//{*}t"))
                self.assertIn(expected, text)
                notes = deck.read(f"ppt/notesSlides/notesSlide{n}.xml")
                self.assertNotIn(b"{{notes}}", notes)
        (self.folder / "strategy.md").unlink()
        pptx.unlink()
        with patch.dict(os.environ, clear=True), patch.object(run_api, "api_key", side_effect=AssertionError):
            self.assertEqual(self.invoke(self.resume)[0], 0)
            self.assertEqual(pptx.read_bytes(), original)
            pptx.write_bytes(original + b"local PowerPoint edit")
            self.assertEqual(self.invoke(self.resume)[0], 0)
            self.assertTrue(pptx.read_bytes().endswith(b"local PowerPoint edit"))
        self.assertEqual(len(self.requests), 3)
        for path, auth, payload in self.requests:
            self.assertEqual(path, "/v1/responses")
            self.assertEqual(auth, "Bearer dummy-key-for-local-http")
            self.assertFalse(payload["store"])
            self.assertNotIn("UNLISTED-DOCUMENT", payload["input"])
            self.assertNotIn("dummy-key-for-local-http", payload["input"])
        for path in self.folder.iterdir():
            self.assertNotIn(b"dummy-key-for-local-http", path.read_bytes())
        self.assertIn("Коммуникационная стратегия", (self.folder / "strategy.md").read_text())

    def test_limit_invalid_key_and_unverified_quote(self):
        self.replies.append((401, {"error": "dummy-key-for-local-http"}))
        self.assertEqual(self.invoke(self.new + ["--max-calls", "1"])[0], 1)
        self.assertIn("Лимит", self.invoke(self.resume)[1])
        self.assertEqual(len(self.requests), 1)
        self.research["evidence"][0]["quote"] = "Выдуманная цитата"
        self.reply(self.research)
        self.assertIn("Цитата", self.invoke(self.resume + ["--max-calls", "2"])[1])
        self.assertFalse((self.folder / "comparison.md").exists())


if __name__ == "__main__":
    unittest.main()
