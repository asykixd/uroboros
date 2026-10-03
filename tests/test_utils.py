import asyncio
import threading

from telethon.errors import UsernameNotOccupiedError

from uroboros import utils


class Client:
    def __init__(self):
        self.sent = []

    async def get_entity(self, target):
        if target == "@nobody":
            raise UsernameNotOccupiedError(request=None)
        return f"entity:{target}"

    async def send_file(self, chat_id, file, **kwargs):
        self.sent.append((chat_id, file, kwargs))
        return "sent"


class Msg:
    def __init__(self, text=".cmd", *, reply=None, private=False, out=True, sender="me"):
        self.raw_text = text
        self.client = Client()
        self.out = out
        self.id = 10
        self.chat_id = -100123
        self._reply = reply
        self.is_reply = reply is not None
        self.reply_to_msg_id = 5 if reply is not None else None
        self.is_private = private
        self._sender = sender
        self.deleted = False

    async def get_reply_message(self):
        return self._reply

    async def get_sender(self):
        return self._sender

    async def get_chat(self):
        return "chat"

    async def delete(self):
        self.deleted = True


def run(coro):
    return asyncio.run(coro)


def test_get_target_prefers_reply():
    assert run(utils.get_target(Msg(".ban @x", reply=Msg(sender="author")))) == "author"


def test_get_target_from_argument():
    assert run(utils.get_target(Msg(".ban @someone"))) == "entity:@someone"
    assert run(utils.get_target(Msg(".ban 42"))) == "entity:42"
    assert run(utils.get_target(Msg(".ban"), "-100500")) == "entity:-100500"
    assert run(utils.get_target(Msg(".ban @nobody"))) is None


def test_get_target_private_chat_and_nothing():
    assert run(utils.get_target(Msg(".ban", private=True))) == "chat"
    assert run(utils.get_target(Msg(".ban"))) is None


def test_get_reply_and_user():
    reply = Msg(sender="author")
    assert run(utils.get_reply(Msg(reply=reply))) is reply
    assert run(utils.get_reply(Msg())) is None
    assert run(utils.get_user(Msg(sender="me"))) == "me"
    assert utils.get_chat_id(Msg()) == -100123


def test_answer_file_replies_and_deletes_command():
    message = Msg(reply=Msg())
    assert run(utils.answer_file(message, b"data", "<b>подпись</b>")) == "sent"
    ((chat_id, file, kwargs),) = message.client.sent
    assert (chat_id, file, kwargs["reply_to"], kwargs["caption"]) == (-100123, b"data", 5, "<b>подпись</b>")
    assert message.deleted


def test_run_sync_runs_in_thread():
    main = threading.get_ident()
    assert run(utils.run_sync(lambda x, y=1: (x + y, threading.get_ident() != main), 2, y=3)) == (5, True)
