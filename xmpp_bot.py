import slixmpp


class MUCBot(slixmpp.ClientXMPP):

    def __init__(self, jid, password):
        slixmpp.ClientXMPP.__init__(self, jid, password)

        self.add_event_handler("session_start", self.start)

        # self.register_plugin('xep_0030')  # Service Discovery
        # self.register_plugin('xep_0199')  # XMPP Ping
        # self.register_plugin('xep_0045')  # Multi-User Chat
        # self.register_plugin('xep_0461')  # Message Replies
        # self.register_plugin('xep_0363')  # HTTP file upload

    async def start(self, event):
        await self.get_roster()
        self.send_presence()
        self.send_message(
            mto="jjj333@pain.agency",
            mbody="Hello there",
            # mtype="chat",
        )

    async def muc_message(self, msg):
        print(f"XMPP received message from {msg['from']} with message: {msg['body']}")

        # if presence['muc']['nick'] != self.nick:
        #     print(f"User online: {presence['muc']['nick']} (Role: {presence['muc']['role']})")


def create_bot(login):
    xmpp = MUCBot(login["jid"], login["password"])

    # Connect to the XMPP server and start processing XMPP stanzas.
    future = xmpp.connect()
    # asyncio.get_event_loop().run_forever()

    return xmpp, future
