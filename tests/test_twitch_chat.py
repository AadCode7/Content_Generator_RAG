import unittest

from gta_researcher.twitch_chat import parse_privmsg


class TwitchChatParserTests(unittest.TestCase):
    def test_parse_privmsg(self):
        message = parse_privmsg(":sampleuser!sampleuser@sampleuser.tmi.twitch.tv PRIVMSG #samplechannel :That was amazing!")
        self.assertIsNotNone(message)
        self.assertEqual(message.username, "sampleuser")
        self.assertEqual(message.channel, "samplechannel")
        self.assertEqual(message.text, "That was amazing!")
        self.assertIsNotNone(message.received_at.tzinfo)

    def test_ignore_ping_and_non_message_lines(self):
        self.assertIsNone(parse_privmsg("PING :tmi.twitch.tv"))
        self.assertIsNone(parse_privmsg(":server NOTICE * :Login authentication failed"))

    def test_accept_oauth_prefix(self):
        from gta_researcher.twitch_chat import TwitchIRCReader
        reader = TwitchIRCReader("viewer", "oauth:abc123", "#SomeChannel")
        self.assertEqual(reader.oauth_token, "abc123")
        self.assertEqual(reader.channel, "somechannel")


if __name__ == "__main__":
    unittest.main()
