from zope.interface import implementer

from twisted.internet.endpoints import serverFromString

from twisted.internet.defer import Deferred, inlineCallbacks
from twisted.internet import reactor

from twisted.protocols.amp import AmpBox, Command, IBoxSender, BoxDispatcher, Integer

from tubes.protocol import flowFountFromEndpoint
from tubes.listening import Listener
from tubes.itube import ISegment
from tubes.tube import Pump, series
from tubes.framing import packedPrefixToStrings

class StringsToBoxes(Pump):

    inputType = None            # I... Packet? IString? IDatagram?
    outputType = None           # AmpBox -> TODO, implement classes.

    state = 'new'

    def received(self, item):
        return getattr(self, 'received_' + self.state)(item)


    def received_new(self, item):
        self._currentBox = AmpBox()
        return self.received_key(item)


    def received_key(self, item):
        if item:
            self._currentKey = item
            self.state = 'value'
        else:
            self.state = 'new'
            yield self._currentBox


    def received_value(self, item):
        self._currentBox[self._currentKey] = item
        self.state = 'key'



class BoxesToData(Pump):
    """
    Shortcut: I want to go from boxes directly to data.
    """
    inputType = None            # AmpBox
    outputType = ISegment

    def received(self, item):
        yield item.serialize()


@implementer(IBoxSender)
class BufferingBoxSender(object):
    def __init__(self):
        self.boxesToSend = []

    def sendBox(self, box):
        self.boxesToSend.append(box)

    def unhandledError(failure):
        from twisted.python import log
        log.err(failure)


class BoxConsumer(Pump):

    inputType = None            # AmpBox
    outputType = None           # AmpBox

    def __init__(self, boxReceiver):
        self.boxReceiver = boxReceiver
        self.bbs = BufferingBoxSender(self)


    def started(self):
        self.boxReceiver.startReceivingBoxes(self.bbs)


    def unhandledError(self, failure):
        failure.printTraceback()


    def received(self, box):
        self.boxReceiver.ampBoxReceived(box)
        boxes = self.bbs.boxesToSend
        self.bbs.boxesToSend = []
        return boxes



class Add(Command):
    arguments = [('a', Integer()),
                 ('b', Integer())]
    response = [('result', Integer())]


class Math(BoxDispatcher):
    @Add.responder
    def add(self, a, b):
        return dict(result=a + b)


def mathFlow(fount):
    fount.flowTo(series(packedPrefixToStrings(16), StringsToBoxes(),
                        BoxConsumer(Math()), BoxesToData(), fount.drain))




@inlineCallbacks
def main():
    serverEndpoint = serverFromString(reactor, "tcp:1234")
    flowFount = yield flowFountFromEndpoint(serverEndpoint)
    flowFount.flowTo(Listener(mathFlow))
    yield Deferred()


from twisted.interne.task import react
from sys import argv
react(main, argv[1:])
