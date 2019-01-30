Chat Relay
==========

Basically an echobot to link chatgroups/-rooms on different servers that use
incompatible protocols


Config
------

Example `config.py`:

```
accounts = {
    'xmpp': {
        'type': 'xmpp',
        'jid': 'relay@example.org',
        'password': 'Very very secret passphrase'
    },
    'fb': {
        'type': 'fbchat',
        'email': 'relay345678@example.org',
        'password': 'Also a very secret passphrase'
    },
}

rooms = {
    'example-fb': {
        'account': 'fb',
        'uid': '1234567890'
    },
    'example-xmpp': {
        'account': 'xmpp',
        'muc': 'example@example.org',
        'nick': '[bot] Relay'
    },
}

relays = [
    ('example-fb', 'example-xmpp'),
]
```
