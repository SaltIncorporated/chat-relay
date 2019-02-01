import mimetypes
import os, os.path
from urllib.request import urlopen, Request

from sleekxmpp import Iq
from sleekxmpp.exceptions import XMPPError
from sleekxmpp.plugins import BasePlugin
from sleekxmpp.plugins.base import register_plugin
from sleekxmpp.xmlstream import register_stanza_plugin
from sleekxmpp.xmlstream import ElementBase


class RequestSlot(ElementBase):

    name           = 'request'
    namespace      = 'urn:xmpp:http:upload:0'
    plugin_attrib  = 'req_upload_slot'
    interfaces     = set(('filename', 'size', 'content-type'))
    sub_interfaces = set()
    is_extension   = False


class Slot(ElementBase):

    name           = 'slot'
    namespace      = 'urn:xmpp:http:upload:0'
    plugin_attrib  = 'slot'
    interfaces     = set()
    sub_interfaces = set()
    is_extension   = False


class Put(ElementBase):

    name           = 'put'
    namespace      = 'urn:xmpp:http:upload:0'
    plugin_attrib  = 'put'
    interfaces     = set(('url',))
    sub_interfaces = set()
    is_extension   = False


class Get(ElementBase):

    name           = 'get'
    namespace      = 'urn:xmpp:http:upload:0'
    plugin_attrib  = 'get'
    interfaces     = set(('url',))
    sub_interfaces = set()
    is_extension   = False



class XEP_0363(BasePlugin):

    xep          = '0363'
    name         = 'xep_0363'
    description  = 'XEP-0363: HTTP File Upload'
    dependencies = set(('xep_0030',))

    def plugin_init(self):
        register_stanza_plugin(Iq, RequestSlot)
        register_stanza_plugin(Iq, Slot)
        register_stanza_plugin(Slot, Put)
        register_stanza_plugin(Slot, Get)

    def post_init(self):
        self.xmpp['xep_0030'].add_feature('urn:xmpp:http:upload:0:request')

    def session_bind(self, jid):
        self.jid = jid
        self.http = None

    def plugin_del(self):
        self.xmpp['xep_0030'].del_feature(feature='urn:xmpp:http:upload:0:request')

    def get_slot(self, path, mime):
        if not self.http:
            items = self.xmpp['xep_0030'].get_items(self.jid.domain, block=True)
            if not self.xmpp['xep_0030'].supports(self.jid.domain, feature='urn:xmpp:http:upload:0'):
                raise XMPPError(text='Could not find HTTP service @ ' + self.jid.domain)
            self.http = self.jid.domain
        size = os.path.getsize(path)
        iq   = self.xmpp.Iq()
        iq['type']                            = 'get'
        iq['to']                              = self.http
        iq['req_upload_slot']['filename']     = os.path.basename(path)
        iq['req_upload_slot']['size']         = str(size)
        iq['req_upload_slot']['content-type'] = mime[0]
        result = iq.send(block=True)
        return result['slot']['put']['url'], result['slot']['get']['url']

    def upload_file(self, path, mime=None):
        if not mime: mime = mimetypes.guess_type(path)
        put_url, get_url = self.get_slot(path, mime)
        with open(path, 'rb') as f:
            request = Request(put_url, f.read(), {
                'Content-Type': mime[0],
                'Content-Length': str(os.path.getsize(path)),
            }, method='PUT')
        os.remove(path)
        response = urlopen(request)
        if response.getcode() != 201:
            raise XMPPError(response.getcode())
        return get_url


register_plugin(XEP_0363)
