#!venv/bin/python3

from ast import literal_eval
from fbchat import Client as ClientFB, ThreadType
from fbchat.models import \
                   Message as MessageFB, \
                Attachment as AttachmentFB, \
           AudioAttachment as AudioAttachmentFB, \
            FileAttachment as FileAttachmentFB, \
           ImageAttachment as ImageAttachmentFB, \
    LiveLocationAttachment as LiveLocationAttachmentFB, \
        LocationAttachment as LocationAttachmentFB, \
           ShareAttachment as ShareAttachmentFB, \
           VideoAttachment as VideoAttachmentFB, \
       FBchatFacebookError
from sleekxmpp import ClientXMPP
from sleekxmpp.exceptions import IqError, IqTimeout
from queue import Queue
from threading import Thread
from urllib.request import urlretrieve
import time
import logging

import config
import xmpp_plugins.xep_0363 as xep_0363

"""
Models
"""
class Attachment():

    def __init__(self, url):
        self.url = url


class AudioAttachment(Attachment):

    pass


class FileAttachment(Attachment):

    pass


class ImageAttachment(Attachment):

    pass


class VideoAttachment(Attachment):

    pass


class Message():

    pass


class TextMessage(Message):

    def __init__(self, user, text):
        self.user = user
        self.text = text


class AttachmentMessage(Message):

    def __init__(self, user, attachments):
        self.user = user
        self.attachments = attachments


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
        self.client.register_plugin('xep_0363', module=xep_0363) # HTTP File Upload
        self.client.add_event_handler('session_start', self.session_start)
        self.client.add_event_handler('groupchat_message', self.muc_message)
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
            self.client.send_message(mto=room, mbody=f'<{msg.user}> {msg.text}', mtype='groupchat')
        elif type(msg) is AttachmentMessage:
            self.client.send_message(mto=room, mbody=f'{msg.user} sent:', mtype='groupchat')
            for a in msg.attachments:
                if type(a) is ImageAttachment:
                    name = '/tmp/' + a.url.split('?', 1)[0].rsplit('/')[-1]
                    urlretrieve(a.url, name)
                    url = self.client['xep_0363'].upload_file(name)
                else:
                    url = a.url
                self.client.send_message(mto=room, mbody=url, mtype='groupchat')

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
                if message_object.text != None:
                    m = TextMessage(name, message_object.text)
                    room.receive(m)
                if len(message_object.attachments) > 0:
                    atts = []
                    for a in message_object.attachments:
                        if type(a) is AudioAttachmentFB:
                            atts.append(AudioAttachment(a.url))
                        elif type(a) is FileAttachmentFB:
                            atts.append(FileAttachment(a.url))
                        elif type(a) is LocationAttachmentFB:
                            atts.append(Attachment(a.url))
                        elif type(a) is ImageAttachmentFB:
                            while True:
                                try:
                                    atts.append(ImageAttachment(self.client.fetchImageUrl(a.uid)))
                                    break
                                except FBchatFacebookError as e:
                                    #if e.fb_error_code == '1357031':
                                    #     # Facebook is being retarded. Try again
                                    #    time.sleep(100)
                                    #else:
                                    #    raise
                                    raise
                        elif type(a) is LiveLocationAttachmentFB:
                            atts.append(Attachment('LiveLocationAttachmentFB (no url)'))
                        elif type(a) is ShareAttachmentFB:
                            atts.append(Attachment(a.original_url))
                        elif type(a) is VideoAttachmentFB:
                            atts.append(VideoAttachment(a.preview_url))
                    m = AttachmentMessage(name, atts)
                    room.receive(m)

    def send(self, msg, uid):
        if type(msg) is TextMessage:
            m = MessageFB(text=f'<{msg.user}> {msg.text}')
        elif type(msg) is AttachmentMessage:
            m = MessageFB(attachments=[a.url for a in msg.attachments])
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
        client.client['xep_0045'].joinMUC(room, nick)

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
