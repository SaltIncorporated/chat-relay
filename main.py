#!venv/bin/python3

from ast import literal_eval
from fbchat import Client as ClientFB, ThreadType
from fbchat.models import Message as MessageFB
from sleekxmpp import ClientXMPP
from sleekxmpp.exceptions import IqError, IqTimeout
from queue import Queue
from threading import Thread
import logging

import config

"""
Models
"""
class Message():
    pass

class TextMessage():
    def __init__(self, user, text):
        self.text = '<' + user + '> ' + text


"""
Base classes
"""
class Client():

    def listen(self):
        raise NotImplementedError()


class Room():

    def __init__(self):
        self.forwards = []

    def send(self, msg):
        raise NotImplementedError()

    def receive(self, msg):
        for f in self.forwards:
            f.send(msg)

"""
Clients
"""
class XMPPClient(Client):

    def __init__(self, jid, password):
        super().__init__()
        self.rooms  = {}
        self.jid    = jid
        self.client = ClientXMPP(jid, password)
        self.client.register_plugin('xep_0030') # Service Discovery
        self.client.register_plugin('xep_0045') # Multi-User Chat
        self.client.register_plugin('xep_0199') # XMPP Ping
        self.client.add_event_handler("session_start", self.session_start)
        self.client.add_event_handler("groupchat_message", self.muc_message)
        self.client.connect()

    def session_start(self, event):
        self.client.send_presence()
        self.client.get_roster()

    def muc_message(self, msg):
        room = msg['mucroom']
        if room in self.rooms:
            room = self.rooms[room]
            if msg['mucnick'] != room.nick:
                m = TextMessage(msg['mucnick'], msg['body'])
                room.receive(m)

    def send(self, msg, room):
        if type(msg) is TextMessage:
            self.client.send_message(mto=room, mbody=msg.text, mtype='groupchat')

    def listen(self):
        self.client.process(block=False)


class FBChatClient(Client):

    _authors_map = {}

    def __init__(self, email, password):
        super().__init__()
        self.rooms  = {}
        try:
            with open(email + '.fbcookies', 'r') as f:
                session = literal_eval(f.read())
        except FileNotFoundError:
            session = None
        self.client = ClientFB(email, password, session_cookies=session, logging_level=10000)
        with open(email + '.fbcookies', 'w') as f:
            f.write(str(self.client.getSession()))
        self.client.onMessage = self.onMessage

    def get_author_name(self, uid):
        if uid not in self._authors_map:
            infos = self.client.fetchUserInfo(uid)
            for i in infos:
               self._authors_map[i] = infos[i]
        return self._authors_map[uid].first_name

    def onMessage(self, author_id, message_object, thread_id, thread_type, **kwargs):
        if thread_id in self.rooms:
            room = self.rooms[thread_id]
            if author_id != self.client.uid:
                name = self.get_author_name(message_object.author)
                m = TextMessage(name, message_object.text)
                room.receive(m)

    def send(self, msg, uid):
        if type(msg) is TextMessage:
            m = MessageFB(text=msg.text)
            self.client.send(m, thread_id=uid, thread_type=ThreadType.GROUP)

    def listen(self):
        Thread(target=self.client.listen, daemon=True).start()


"""
Rooms
"""
class XMPPRoom(Room):

    def __init__(self, client, room, nick):
        super().__init__()
        self.client = client
        self.room   = room
        self.nick   = nick
        client.rooms[room] = self
        client.client.plugin['xep_0045'].joinMUC(room, nick)

    def send(self, msg):
        self.client.send(msg, self.room)


class FBChatRoom(Room):

    def __init__(self, client, uid):
        super().__init__()
        self.client = client
        self.uid    = uid
        client.rooms[uid] = self

    def send(self, msg):
        self.client.send(msg, self.uid)


"""
Relays
"""

def create_relay(r1, r2):
    r1.forwards.append(r2)
    r2.forwards.append(r1)


"""
Main
"""
if __name__ == '__main__':
    #logging.basicConfig(level=logging.ERROR,
    #                    format='%(levelname)-8s %(message)s')

    clients = {}
    rooms   = {}

    # Connect the accounts
    for k,v in config.accounts.items():
        t = v['type']
        if t == 'xmpp':
            c = XMPPClient(v['jid'], v['password'])
        elif t == 'fbchat':
            c = FBChatClient(v['email'], v['password'])
        clients[k] = c

    # Create the room objects
    for k,v in config.rooms.items():
        c = clients[v['account']]
        if type(c) is XMPPClient:
            room = XMPPRoom(c, v['muc'], v['nick'])
        elif type(c) is FBChatClient:
            room = FBChatRoom(c, v['uid'])
        rooms[k] = room

    # Create the relays between the rooms
    for v in config.relays:
        create_relay(rooms[v[0]], rooms[v[1]])

    # Start listening on all accounts
    for _, c in clients.items():
        c.listen()

    # Wait until the end of times
    from time import sleep
    while True:
        sleep(9999999)
