import unittest
from links import parse_message_link


class TestTelegramLinks(unittest.TestCase):
    def test_private(self):
        ref = parse_message_link("https://t.me/c/123456789/987?single")
        self.assertEqual((ref.chat, ref.message_id, ref.private), (-100123456789, 987, True))

    def test_topic(self):
        ref = parse_message_link("https://t.me/c/12345/88/999")
        self.assertEqual(ref.message_id, 999)

    def test_public(self):
        ref = parse_message_link("https://t.me/publicMusic/123")
        self.assertEqual((ref.chat, ref.message_id), ("publicMusic", 123))

    def test_bad(self):
        for url in (
            "http://t.me/c/1/2", "https://evil.com/c/1/2",
            "https://t.me/+ABCXYZ", "https://t.me/c/notanumber/2",
            "https://t.me/c/1/0", "https://t.me/example", "https://t.me/joinchat/123",
        ):
            self.assertIsNone(parse_message_link(url), url)


if __name__ == "__main__":
    unittest.main()