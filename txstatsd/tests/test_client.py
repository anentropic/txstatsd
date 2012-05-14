"""Tests for the various client classes."""

from twisted.internet import reactor
from twisted.internet.defer import inlineCallbacks, Deferred
from twisted.python import log
from twisted.trial.unittest import TestCase

from txstatsd.client import (
    StatsDClientProtocol, TwistedStatsDClient, UdpStatsDClient,
    ConsistentHashingClient)


class FakeClient(object):

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.data = []

    def __str__(self):
        return "%s:%d" % (self.host, self.port)

    def write(self, data):
        self.data.append(data)


class TestClient(TestCase):

    def setUp(self):
        super(TestClient, self).setUp()
        self.client = None
        self.exception = None

    def tearDown(self):
        if self.client:
            self.client.transport.stopListening()
        super(TestClient, self).tearDown()

    def test_twistedstatsd_write_with_wellformed_address(self):
        self.client = TwistedStatsDClient('127.0.0.1', 8000)
        protocol = StatsDClientProtocol(self.client)
        reactor.listenUDP(0, protocol)

        def ensure_bytes_sent(bytes_sent):
            self.assertEqual(bytes_sent, len('message'))

        def exercise(callback):
            self.client.write('message', callback=callback)

        d = Deferred()
        d.addCallback(ensure_bytes_sent)
        reactor.callWhenRunning(exercise, d.callback)
        return d

    @inlineCallbacks
    def test_twistedstatsd_with_malformed_address_and_errback(self):
        def ensure_exception_raised(ignore):
            self.assertTrue(self.exception.startswith("DNS lookup failed"))

        def capture_exception_raised(failure):
            self.exception = failure.getErrorMessage()

        yield TwistedStatsDClient(
            '256.0.0.0', 1,
            resolver_errback=capture_exception_raised)

        d = Deferred()
        d.addCallback(ensure_exception_raised)
        reactor.callLater(.5, d.callback, None)
        yield d

    @inlineCallbacks
    def test_twistedstatsd_with_malformed_address_and_no_errback(self):
        def ensure_exception_raised(ignore):
            self.assertTrue(self.exception.startswith("DNS lookup failed"))

        def capture_exception_raised(failure):
            self.exception = failure.getErrorMessage()

        self.patch(log, "err", capture_exception_raised)

        yield TwistedStatsDClient('256.0.0.0', 1)

        d = Deferred()
        d.addCallback(ensure_exception_raised)
        reactor.callLater(.5, d.callback, None)
        yield d

    def test_udpstatsd_wellformed_address(self):
        client = UdpStatsDClient('localhost', 8000)
        self.assertEqual(client.host, '127.0.0.1')
        client = UdpStatsDClient(None, None)
        self.assertEqual(client.host, None)

    def test_udpstatsd_malformed_address(self):
        self.assertRaises(ValueError,
                          UdpStatsDClient, 'localhost', -1)
        self.assertRaises(ValueError,
                          UdpStatsDClient, 'localhost', 'malformed')
        self.assertRaises(ValueError,
                          UdpStatsDClient, 0, 8000)

    def test_udpstatsd_socket_nonblocking(self):
        client = UdpStatsDClient('localhost', 8000)
        client.connect()
        # According to the python docs (and the source, I've checked)
        # setblocking(0) is the same as settimeout(0.0).
        self.assertEqual(client.socket.gettimeout(), 0.0)


class TestConsistentHashingClient(TestCase):

    def test_hash_with_single_client(self):
        clients = [
            FakeClient("127.0.0.1", 10001),
            ]
        client = ConsistentHashingClient(clients)
        client.write("foo 1 42")
        client.write("bar 1 42")
        client.write("pak 1 42")
        self.assertEqual(clients[0].data, ["foo 1 42",
                                           "bar 1 42",
                                           "pak 1 42"])

    def test_hash_with_two_clients(self):
        clients = [
            FakeClient("127.0.0.1", 10001),
            FakeClient("127.0.0.1", 10002),
            ]
        client = ConsistentHashingClient(clients)
        client.write("foo 1 42")
        client.write("bar 1 42")
        client.write("pak 1 42")
        self.assertEqual(clients[0].data, ["foo 1 42",
                                           "pak 1 42"])
        self.assertEqual(clients[1].data, ["bar 1 42"])

    def test_hash_with_three_clients(self):
        clients = [
            FakeClient("127.0.0.1", 10001),
            FakeClient("127.0.0.1", 10002),
            FakeClient("127.0.0.1", 10003),
            ]
        client = ConsistentHashingClient(clients)
        client.write("foo 1 42")
        client.write("bar 1 42")
        client.write("pak 1 42")
        self.assertEqual(clients[0].data, ["foo 1 42"])
        self.assertEqual(clients[1].data, ["bar 1 42"])
        self.assertEqual(clients[2].data, ["pak 1 42"])
