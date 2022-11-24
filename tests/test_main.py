# -*- coding: utf-8 -*-
import asyncio
import ssl

import aiostomp.aiostomp
from aiostomp.test_utils import AsyncTestCase, unittest_run_loop

from aiostomp.aiostomp import AioStomp, StompReader, StompProtocol, AioStompStats
from aiostomp.subscription import Subscription
from aiostomp.errors import StompError, StompDisconnectedError, ExceededRetryCount
from aiostomp.frame import Frame

from asynctest import CoroutineMock, Mock, patch


class TestStompStats(AsyncTestCase):
    def test_can_increment_a_field(self):
        stats = AioStompStats()
        stats.increment("sent_msg")

        self.assertEqual(stats.connection_stats[0]["sent_msg"], 1)

    def test_can_increment_a_missing_field(self):
        stats = AioStompStats()
        stats.increment("something")

        self.assertEqual(stats.connection_stats[0]["something"], 1)

    @patch("aiostomp.aiostomp.logger")
    def test_can_print_stats(self, logger_mock):
        stats = AioStompStats()
        stats.increment("sent_msg")

        stats.print_stats()

        self.assertEqual(logger_mock.info.call_count, 5)


class TestStompReader(AsyncTestCase):
    @unittest_run_loop
    async def test_accept_version_header(self):
        stomp = StompReader(None, self.loop)
        self.assertEqual(stomp._connect_headers["accept-version"], "1.1")

    @patch("aiostomp.aiostomp.StompReader.connect")
    @unittest_run_loop
    async def test_connection_can_be_made(self, connect_mock):
        stomp = StompReader(None, self.loop)

        transport = Mock()

        stomp.connection_made(transport)

        connect_mock.assert_called_once()

    @patch("aiostomp.aiostomp.StompReader.connect")
    @unittest_run_loop
    async def test_transport_is_closed_connection_close(self, connect_mock):
        stomp = StompReader(None, self.loop)

        transport = Mock()

        stomp.connection_made(transport)

        connect_mock.assert_called_once()

        stomp.close()

    def test_connection_can_be_lost(self):
        frame_handler = Mock()
        heartbeater = Mock()

        stomp = StompReader(frame_handler, self.loop)
        stomp.heartbeater = heartbeater
        exc = Exception()

        stomp.connection_lost(exc)

        heartbeater.shutdown.assert_called_once()
        frame_handler.connection_lost.assert_called_with(exc)

    def test_connection_can_be_lost_no_heartbeat(self):
        frame_handler = Mock()
        heartbeater = Mock()

        stomp = StompReader(frame_handler, self.loop)
        stomp.heartbeater = None
        exc = Exception()

        stomp.connection_lost(exc)

        heartbeater.shutdown.assert_not_called()
        frame_handler.connection_lost.assert_called_with(exc)

    def test_can_close_connection(self):
        frame_handler = Mock()
        heartbeater = Mock()

        stomp = StompReader(frame_handler, self.loop)
        stomp.heartbeater = heartbeater

        stomp.close()

        heartbeater.shutdown.assert_called_once()

    def test_can_close_connection_no_heartbeat(self):
        frame_handler = Mock()
        heartbeater = Mock()

        stomp = StompReader(frame_handler, self.loop)
        stomp.heartbeater = None

        stomp.close()

        heartbeater.shutdown.assert_not_called()

    @patch("aiostomp.aiostomp.StompReader.connection_lost")
    def test_can_receive_eof(self, connection_lost_mock):
        stomp = StompReader(None, self.loop)
        stomp.eof_received()

        connection_lost_mock.assert_called_once()

    @unittest_run_loop
    async def test_send_frame_can_raise_error(self):
        stomp = StompReader(None, self.loop)
        stomp._transport = None

        with self.assertRaises(StompDisconnectedError):
            stomp.send_frame("SUBSCRIBE", {"ack": "auto"}, "ç")

    @unittest_run_loop
    async def test_can_send_frame(self):
        stomp = StompReader(None, self.loop)
        stomp._transport = Mock()

        stomp.send_frame("SUBSCRIBE", {"ack": "auto"}, "ç")

        stomp._transport.write.assert_called_with(
            b"SUBSCRIBE\n" b"ack:auto\n" b"\n" b"\xc3\xa7\x00"
        )

    @unittest_run_loop
    async def test_can_connect(self):
        stomp = StompReader(
            None, self.loop, heartbeat={"enabled": True, "cx": 1000, "cy": 1000}
        )
        stomp._transport = Mock()

        stomp.connect()
        stomp._transport.write.assert_called_with(
            b"CONNECT\naccept-version:1.1\nheart-beat:1000,1000\n\n\x00"
        )

    @unittest_run_loop
    async def test_can_connect_with_username(self):
        stomp = StompReader(
            None,
            self.loop,
            heartbeat={"enabled": True, "cx": 1000, "cy": 1000},
            username="pkiefer",
        )
        stomp._transport = Mock()

        stomp.connect()
        stomp._transport.write.assert_called_with(
            b"CONNECT\naccept-version:1.1\nheart-beat:1000,1000\nlogin:pkiefer\n\n\x00"
        )  # noqa

    @unittest_run_loop
    async def test_can_connect_with_password(self):
        stomp = StompReader(
            None,
            self.loop,
            heartbeat={"enabled": True, "cx": 1000, "cy": 1000},
            password="pass",
        )
        stomp._transport = Mock()

        stomp.connect()
        stomp._transport.write.assert_called_with(
            b"CONNECT\naccept-version:1.1\nheart-beat:1000,1000\npasscode:pass\n\n\x00"
        )  # noqa

    @unittest_run_loop
    async def test_can_connect_with_login_pass(self):
        stomp = StompReader(
            None,
            self.loop,
            heartbeat={"enabled": True, "cx": 1000, "cy": 1000},
            username="pkiefer",
            password="pass",
        )
        stomp._transport = Mock()

        stomp.connect()
        stomp._transport.write.assert_called_with(
            b"CONNECT\naccept-version:1.1\nheart-beat:1000,1000\nlogin:pkiefer\npasscode:pass\n\n\x00"
        )  # noqa

    @patch("aiostomp.aiostomp.StompReader._handle_connect")
    @unittest_run_loop
    async def test_can_process_connected_frame(self, connect_handle_mock):
        stomp = StompReader(None, self.loop)

        stomp.data_received(b"CONNECTED\n" b"heart-beat:1000,1000\n\n" b"{}\x00")

        await asyncio.sleep(0.001)
        connect_handle_mock.assert_called_once()

    @patch("aiostomp.aiostomp.StompHeartbeater")
    @unittest_run_loop
    async def test_can_handle_connected_frame_without_heartbeat(
        self, heartbeater_klass_mock
    ):
        frame = Frame("CONNECTED", {}, "{}")

        stomp = StompReader(None, self.loop)
        await stomp._handle_connect(frame)

        heartbeater_klass_mock.assert_not_called()

    @patch("aiostomp.aiostomp.StompHeartbeater")
    @unittest_run_loop
    async def test_can_handle_connected_frame_with_heartbeat(
        self, heartbeater_klass_mock
    ):
        frame = Frame("CONNECTED", {"heart-beat": "1000,1000"}, "{}")

        heartbeater_mock = heartbeater_klass_mock.return_value
        heartbeater_mock.start = CoroutineMock()

        stomp = StompReader(
            None, self.loop, heartbeat={"enabled": True, "cx": 1000, "cy": 1000}
        )
        stomp._transport = Mock()
        await stomp._handle_connect(frame)

        heartbeater_klass_mock.assert_called_with(
            stomp._transport, interval=1000, logger=aiostomp.aiostomp.logger
        )
        heartbeater_mock.start.assert_called_once()

    @patch("aiostomp.aiostomp.StompHeartbeater")
    @unittest_run_loop
    async def test_can_handle_connected_frame_with_heartbeat_disabled(
        self, heartbeater_klass_mock
    ):
        frame = Frame("CONNECTED", {"heart-beat": "1000,1000"}, "{}")

        heartbeater_mock = heartbeater_klass_mock.return_value
        heartbeater_mock.start = CoroutineMock()

        stomp = StompReader(
            None, self.loop, heartbeat={"enabled": False, "cx": 0, "cy": 0}
        )
        stomp._transport = Mock()
        await stomp._handle_connect(frame)

        heartbeater_klass_mock.assert_not_called

    @patch("aiostomp.aiostomp.StompReader._handle_message")
    @unittest_run_loop
    async def test_can_process_messages(self, message_handle_mock):
        stomp = StompReader(None, self.loop)

        await asyncio.sleep(0.001)

        stomp.data_received(
            b"MESSAGE\n"
            b"subscription:1\n"
            b"message-id:007\n"
            b"destination:/topic/test\n"
            b"\n"
            b"blahh-line-a\n\nblahh-line-b\n\nblahh-line-c\x00"
        )

        await asyncio.sleep(0.001)
        message_handle_mock.assert_called_once()

    @patch("aiostomp.aiostomp.StompReader._handle_message")
    @unittest_run_loop
    async def test_can_process_long_messages(self, message_handle_mock):
        stomp = StompReader(None, self.loop)

        await asyncio.sleep(0.001)

        data = (
            b"MESSAGE\n"
            b"content-length:14\nexpires:0\ndestination:/topic/"
            b"xxxxxxxxxxxxxxxxxxxxxxxxxl"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c363\\c-1\\c1\\c463859\npersistent:true\ntimestamp"
            b":1548945234003\n\n222.222.22.222"
            b"\x00\nMESSAGE\ncontent-length:12\nexpires:0\ndestination:"
            b"/topic/xxxxxxxxxxxxxxxxxxxxxxxxxx"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c363\\c-1\\c1\\c463860\npersistent:true\ntimestamp"
            b":1548945234005\n\n88.88.888.88"
            b"\x00\nMESSAGE\ncontent-length:11\nexpires:0\ndestination:"
            b"/topic/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c362\\c-1\\c1\\c290793\npersistent:true\ntimestamp"
            b":1548945234005\n\n111.11.1.11"
            b"\x00\nMESSAGE\ncontent-length:14\nexpires:0\ndestination:"
            b"/topic/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c362\\c-1\\c1\\c290794\npersistent:true\ntimestamp:"
            b"1548945234005\n\n222.222.22.222"
            b"\x00\nMESSAGE\ncontent-length:12\nexpires:0\ndestination:"
            b"/topic/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c362\\c-1\\c1\\c290795\npersistent:true\ntimestamp:"
            b"1548945234005\n\n88.88.888.88\x00\nMESS"
        )

        stomp.data_received(data)
        await asyncio.sleep(0.001)

        self.assertEqual(message_handle_mock.call_count, 5)
        self.assertEqual(bytes(stomp._protocol.current_command), b"MESS")

    @patch("aiostomp.aiostomp.StompReader._handle_message")
    @unittest_run_loop
    async def test_can_process_long_partial_messages(self, message_handle_mock):
        stomp = StompReader(None, self.loop)

        await asyncio.sleep(0.001)

        stomp.data_received(
            b"MESSAGE\n"
            b"content-length:14\nexpires:0\ndestination:/topic/"
            b"xxxxxxxxxxxxxxxxxxxxxxxxxl"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
        )
        await asyncio.sleep(0.001)

        stomp.data_received(
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c363\\c-1\\c1\\c463859\npersistent:true\ntimestamp"
            b":1548945234003\n\n222.222.22.222"
            b"\x00\nMESSAGE\ncontent-length:12\nexpires:0\ndestination:"
            b"/topic/xxxxxxxxxxxxxxxxxxxxxxxxxx"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c363\\c-1\\c1\\c463860\npersistent:true\ntimestamp"
            b":1548945234005\n\n88.88.888.88"
            b"\x00\nMESS"
        )
        await asyncio.sleep(0.001)

        stomp.data_received(
            b"AGE\n"
            b"content-length:14\nexpires:0\ndestination:/topic/"
            b"xxxxxxxxxxxxxxxxxxxxxxxxxl"
            b"\nsubscription:1\npriority:4\nActiveMQ.MQTT.QoS:1\nmessage-id"
        )
        await asyncio.sleep(0.001)

        stomp.data_received(
            b":ID\\cxxxxxx-35207-1543430467768-204"
            b"\\c363\\c-1\\c1\\c463859\npersistent:true\ntimestamp"
            b":1548945234003\n\n222.222.22.222"
            b"\x00"
        )
        await asyncio.sleep(0.001)

        self.assertEqual(message_handle_mock.call_count, 3)
        self.assertEqual(b"".join(stomp._protocol.current_command), b"")

    @patch("aiostomp.aiostomp.StompReader._handle_message")
    @unittest_run_loop
    async def test_consecutive_calls_data_received(self, message_handle_mock):
        stomp = StompReader(None, self.loop)

        await asyncio.sleep(0.001)

        stomp.data_received(
            b"MESSAGE\n"
            b"subscription:1\n"
            b"message-id:007\n"
            b"destination:/topic/test\n"
            b"\n"
            b"blahh-line-a\n\nblahh-line-b\n\nblahh-line-c\x00"
        )

        stomp.data_received(
            b"MESSAGE\n"
            b"subscription:1\n"
            b"message-id:007\n"
            b"destination:/topic/test\n"
            b"\n"
            b"blahh-line-a\n\nblahh-line-b\n\nblahh-line-c\x00"
        )

        await asyncio.sleep(0.001)
        self.assertEqual(message_handle_mock.call_count, 2)

    @unittest_run_loop
    async def test_can_handle_message(self):
        frame = Frame("MESSAGE", {"subscription": "123", "message-id": "321"}, "blah")

        handler = CoroutineMock()
        subscription = Subscription("123", 1, "auto", {}, handler)

        frame_handler = Mock()
        frame_handler.get.return_value = subscription

        stomp = StompReader(frame_handler, self.loop)
        await stomp._handle_message(frame)

        handler.assert_called_with(frame, frame.body)

    @unittest_run_loop
    async def test_can_handle_message_with_no_subscription(self):
        frame = Frame("MESSAGE", {"subscription": "123", "message-id": "321"}, "blah")

        handler = CoroutineMock()

        frame_handler = Mock()
        frame_handler.get.return_value = None

        stomp = StompReader(frame_handler, self.loop)
        await stomp._handle_message(frame)

        handler.assert_not_called()

    @patch("aiostomp.aiostomp.StompReader.send_frame")
    @unittest_run_loop
    async def test_can_handle_message_can_ack(self, send_frame_mock):
        frame = Frame("MESSAGE", {"subscription": "123", "message-id": "321"}, "blah")

        handler = CoroutineMock()
        handler.return_value = True
        subscription = Subscription("123", 1, "client", {}, handler)

        frame_handler = Mock()
        frame_handler.get.return_value = subscription

        stomp = StompReader(frame_handler, self.loop)
        await stomp._handle_message(frame)

        handler.assert_called_with(frame, frame.body)
        send_frame_mock.assert_called_with(
            "ACK", {"subscription": "123", "message-id": "321"}
        )

    @patch("aiostomp.aiostomp.StompReader.send_frame")
    @unittest_run_loop
    async def test_can_handle_message_can_nack(self, send_frame_mock):
        frame = Frame("MESSAGE", {"subscription": "123", "message-id": "321"}, "blah")

        handler = CoroutineMock()
        handler.return_value = False
        subscription = Subscription("123", 1, "client-individual", {}, handler)

        frame_handler = Mock()
        frame_handler.get.return_value = subscription

        stomp = StompReader(frame_handler, self.loop)
        await stomp._handle_message(frame)

        handler.assert_called_with(frame, frame.body)
        send_frame_mock.assert_called_with(
            "NACK", {"subscription": "123", "message-id": "321"}
        )

    @patch("aiostomp.aiostomp.StompReader._handle_error")
    @unittest_run_loop
    async def test_can_process_error(self, error_handle_mock):
        stomp = StompReader(None, self.loop)

        stomp.data_received(
            b"ERROR\n"
            b"message:Invalid error, blah, blah, blah\n"
            b"\n"
            b"Detail Error: blah, blah, blah\x00"
        )

        await asyncio.sleep(0.001)
        error_handle_mock.assert_called_once()

    @patch("aiostomp.aiostomp.logger")
    @unittest_run_loop
    async def test_can_handle_error_frame(self, logger_mock):
        frame = Frame(
            "ERROR",
            {"message": "Invalid error, blah, blah, blah"},
            "Detail Error: blah, blahh-line-a",
        )

        frame_handler = Mock()
        frame_handler._on_error = CoroutineMock()

        stomp = StompReader(frame_handler, self.loop)

        await stomp._handle_error(frame)

        frame_handler._on_error.assert_called_once()
        self.assertTrue(isinstance(frame_handler._on_error.call_args[0][0], StompError))

        logger_mock.error.assert_called_with(
            "Received error: Invalid error, blah, blah, blah"
        )
        logger_mock.debug.assert_called_with(
            "Error details: Detail Error: blah, blahh-line-a"
        )

    @patch("aiostomp.aiostomp.StompReader._handle_exception")
    @unittest_run_loop
    async def test_can_process_exception(self, exception_handle_mock):
        stomp = StompReader(None, self.loop)

        stomp.data_received(
            b"SOMETHING\n"
            b"message:Invalid error, blah, blah, blah\n"
            b"\n"
            b"Detail Error: blah, blah, blah\x00"
        )

        await asyncio.sleep(0.001)
        exception_handle_mock.assert_called_once()

    @unittest_run_loop
    async def test_can_handle_exception(self):
        frame = Frame(
            "SOMETHING",
            {"message": "Invalid error, blah, blah, blah"},
            "Detail Error: blah, blahh-line-a",
        )

        stomp = StompReader(None, self.loop)
        with self.assertLogs("aiostomp", level="WARNING") as cm:
            await stomp._handle_exception(frame)
            self.assertEqual(cm.output, ["WARNING:aiostomp:Unhandled frame: SOMETHING"])

    @unittest_run_loop
    async def test_can_process_empty_message(self):
        stomp = StompReader(None, self.loop)
        stomp._protocol = Mock()

        stomp.data_received(None)

        await asyncio.sleep(0.001)
        stomp._protocol.feed_data.assert_not_called()

    @unittest_run_loop
    async def test_can_process_heartbeat(self):
        stomp = StompReader(None, self.loop)
        stomp.data_received(b"\n")

        await asyncio.sleep(0.001)


class TestAioStomp(AsyncTestCase):
    async def setUpAsync(self):
        self.stomp = AioStomp("127.0.0.1", 61613)

    @patch("aiostomp.aiostomp.StompProtocol")
    @unittest_run_loop
    async def test_aiostomp_supports_ssl(self, stom_protocol_mock):
        ssl_context = ssl.create_default_context()
        stomp = AioStomp("127.0.0.1", 61613, ssl_context=ssl_context)

        args, kwargs = stom_protocol_mock.call_args

        self.assertTrue("127.0.0.1" in args)
        self.assertTrue(61613 in args)
        self.assertTrue(stomp in args)
        self.assertTrue(kwargs["ssl_context"] == ssl_context)

    @unittest_run_loop
    async def test_can_connect_to_server(self):
        self.stomp._protocol.connect = CoroutineMock()
        await self.stomp.connect()

        self.stomp._protocol.connect.assert_called_once()
        self.assertTrue(self.stomp._connected)

    @unittest_run_loop
    async def test_can_reconnect_to_server(self):
        self.stomp._protocol.connect = CoroutineMock()
        self.stomp._protocol.connect.side_effect = [OSError(), True]

        await self.stomp.connect()

        self.assertEqual(self.stomp._protocol.connect.call_count, 2)

    @unittest_run_loop
    async def test_can_reconnect_to_server_with_max_attemps(self):
        self.stomp._reconnect_max_attempts = 2
        self.stomp._protocol.connect = CoroutineMock()
        self.stomp._protocol.connect.side_effect = [OSError(), True]

        await self.stomp.connect()

        self.assertEqual(self.stomp._protocol.connect.call_count, 2)

    @unittest_run_loop
    async def test_reconnection(self):
        self.stomp._protocol.connect = CoroutineMock()

        await self.stomp._reconnect()

        self.stomp._protocol.connect.assert_called_once()

    @patch("aiostomp.aiostomp.logger")
    @unittest_run_loop
    async def test_reconnection_error(self, logger_mock):
        self.stomp._reconnect_max_attempts = 1
        self.stomp._reconnect_attempts = 1

        self.stomp._protocol.connect = CoroutineMock()
        self.stomp._protocol.connect.side_effect = OSError()

        self.stomp._on_error = CoroutineMock()

        await self.stomp._reconnect()

        logger_mock.error.assert_called_with("All connections attempts failed.")
        self.assertIsInstance(self.stomp._on_error.call_args[0][0], ExceededRetryCount)
        self.assertEqual(self.stomp._on_error.call_args[0][0].ref, self.stomp)

    @unittest_run_loop
    async def test_can_reconnect_on_connection_lost(self):
        self.stomp._reconnect = CoroutineMock()

        self.stomp.connection_lost(Exception())

        self.stomp._reconnect.assert_called_once()

    @unittest_run_loop
    async def test_no_reconnect_on_close(self):
        self.stomp._reconnect = CoroutineMock()

        self.stomp._closed = True

        self.stomp.connection_lost(Exception())

        self.stomp._reconnect.assert_not_called()
        self.stomp._closed = False

    @patch("aiostomp.aiostomp.StompProtocol.close")
    def test_can_close_connection(self, close_mock):
        self.stomp.close()

        close_mock.assert_called_once()

    def test_can_subscribe(self):
        self.stomp._protocol.subscribe = Mock()

        self.stomp.subscribe("/queue/test")

        self.assertEqual(len(self.stomp._subscriptions), 1)
        self.stomp._protocol.subscribe.assert_not_called()

    def test_can_get_subscription(self):
        self.stomp._protocol.subscribe = Mock()

        subscription = self.stomp.subscribe("/queue/test")

        self.assertEqual(len(self.stomp._subscriptions), 1)
        self.stomp._protocol.subscribe.assert_not_called()

        value = self.stomp.get("1")
        self.assertEqual(value, subscription)

    def test_can_subscribe_when_connected(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._connected = True

        subscription = self.stomp.subscribe("/queue/test")

        self.assertEqual(len(self.stomp._subscriptions), 1)
        self.stomp._protocol.subscribe.assert_called_with(subscription)

    @unittest_run_loop
    async def test_subscribe_after_connection(self):
        self.stomp._protocol.connect = CoroutineMock()
        self.stomp._protocol.subscribe = Mock()

        self.stomp.subscribe("/queue/test")

        self.assertEqual(len(self.stomp._subscriptions), 1)
        self.stomp._protocol.subscribe.assert_not_called()

        await self.stomp.connect()

        self.assertTrue(self.stomp._connected)
        self.stomp._protocol.subscribe.assert_called_once()

    def test_can_unsubscribe(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._protocol.unsubscribe = Mock()
        self.stomp._connected = True

        subscription = self.stomp.subscribe("/queue/test")

        self.assertEqual(len(self.stomp._subscriptions), 1)

        self.stomp.unsubscribe(subscription)

        self.stomp._protocol.unsubscribe.assert_called_with(subscription)
        self.assertEqual(len(self.stomp._subscriptions), 0)

    def test_cannot_unsubscribe_when_not_subcribed(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._protocol.unsubscribe = Mock()
        self.stomp._connected = True

        subscription = self.stomp.subscribe("/queue/test")
        subscription.id = 2

        self.assertEqual(len(self.stomp._subscriptions), 1)

        self.stomp.unsubscribe(subscription)

        self.stomp._protocol.unsubscribe.assert_not_called()
        self.assertEqual(len(self.stomp._subscriptions), 1)

    def test_can_send_message_with_body_utf8(self):
        send_mock = Mock()
        self.stomp._protocol.send = send_mock

        self.stomp.send(
            "/topic/test", headers={"my-header": "my-value"}, body="my body utf-8 ç"
        )

        send_mock.assert_called_with(
            {
                "destination": "/topic/test",
                "my-header": "my-value",
                "content-length": 16,
            },
            b"my body utf-8 \xc3\xa7",
        )

    def test_can_send_message_with_body_binary(self):
        send_mock = Mock()
        self.stomp._protocol.send = send_mock

        self.stomp.send(
            "/topic/test", headers={"my-header": "my-value"}, body=b"\xc3\xa7"
        )

        send_mock.assert_called_with(
            {
                "destination": "/topic/test",
                "my-header": "my-value",
                "content-length": 2,
            },
            b"\xc3\xa7",
        )

    def test_can_send_message_with_body_without_content_length(self):
        send_mock = Mock()
        self.stomp._protocol.send = send_mock

        self.stomp.send(
            "/topic/test",
            headers={"my-header": "my-value"},
            body="my body utf-8 ç",
            send_content_length=False,
        )

        send_mock.assert_called_with(
            {"destination": "/topic/test", "my-header": "my-value"},
            b"my body utf-8 \xc3\xa7",
        )

    def test_can_send_message_without_body(self):
        send_mock = Mock()
        self.stomp._protocol.send = send_mock

        self.stomp.send("/topic/test", headers={"my-header": "my-value"})

        send_mock.assert_called_with(
            {
                "destination": "/topic/test",
                "my-header": "my-value",
                "content-length": 0,
            },
            b"",
        )

    def test_can_ack_a_frame(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._protocol.ack = Mock()

        self.stomp.subscribe("/queue/test", auto_ack=False)
        self.assertEqual(len(self.stomp._subscriptions), 1)

        frame = Frame("MESSAGE", {"subscription": "1"}, "data")

        self.stomp.ack(frame)

        self.stomp._protocol.ack.assert_called_with(frame)

    def test_can_nack_a_frame(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._protocol.nack = Mock()

        self.stomp.subscribe("/queue/test", auto_ack=False)
        self.assertEqual(len(self.stomp._subscriptions), 1)

        frame = Frame("MESSAGE", {"subscription": "1"}, "data")

        self.stomp.nack(frame)

        self.stomp._protocol.nack.assert_called_with(frame)

    def test_cannot_ack_an_unsubscribed_frame(self):
        self.stomp._protocol.ack = Mock()
        self.assertEqual(len(self.stomp._subscriptions), 0)

        frame = Frame("MESSAGE", {"subscription": "1"}, "data")

        with self.assertLogs() as cm:
            self.stomp.ack(frame)
            self.assertIn("WARNING:aiostomp:Subscription 1 not found", cm.output)
        self.stomp._protocol.ack.assert_not_called()

    def test_cannot_nack_an_unsubscribed_frame(self):
        self.stomp._protocol.nack = Mock()
        self.assertEqual(len(self.stomp._subscriptions), 0)

        frame = Frame("MESSAGE", {"subscription": "1"}, "data")

        with self.assertLogs() as cm:
            self.stomp.nack(frame)
            self.assertIn("WARNING:aiostomp:Subscription 1 not found", cm.output)

        self.stomp._protocol.nack.assert_not_called()

    def test_cannot_ack_an_auto_ack_frame(self):
        self.stomp._protocol.subscribe = Mock()
        self.stomp._protocol.ack = Mock()

        self.stomp.subscribe("/queue/test", auto_ack=True)
        self.assertEqual(len(self.stomp._subscriptions), 1)

        frame = Frame("MESSAGE", {"subscription": "1"}, "data")

        with self.assertLogs() as cm:
            self.stomp.ack(frame)
            self.assertIn(
                "WARNING:aiostomp:Auto ack/nack is enabled. Ignoring call.", cm.output
            )

        self.stomp._protocol.ack.assert_not_called()


class TestStompProtocol(AsyncTestCase):
    async def setUpAsync(self):
        self._handler = Mock()
        self._loop = Mock()
        self._loop.create_connection = CoroutineMock()
        self._tranport = Mock()
        self._protocol = Mock()

        self._loop.create_connection.return_value = (self._tranport, self._protocol)

        self.protocol = StompProtocol(
            self._handler, "127.0.0.1", 61613, loop=self._loop
        )

    @unittest_run_loop
    async def test_can_create_a_connection(self):
        await self.protocol.connect()

        self._loop.create_connection.assert_called_with(
            self.protocol._factory, host="127.0.0.1", port=61613, ssl=None
        )

    @unittest_run_loop
    async def test_can_close(self):
        await self.protocol.connect()
        self.protocol.close()

        self._protocol.close.assert_called_once()

    @unittest_run_loop
    async def test_can_create_a_connection_with_ssl_context(self):
        ssl_context = ssl.create_default_context()
        self.protocol.ssl_context = ssl_context

        await self.protocol.connect()

        self._loop.create_connection.assert_called_with(
            self.protocol._factory, host="127.0.0.1", port=61613, ssl=ssl_context
        )

    @unittest_run_loop
    async def test_can_subscribe(self):
        handler = Mock()
        subscription = Subscription(
            "/queue/123", 1, "client", {"my-header": "my-value"}, handler
        )

        await self.protocol.connect()
        self.protocol.subscribe(subscription)

        self._protocol.send_frame.assert_called_with(
            "SUBSCRIBE",
            {
                "id": 1,
                "destination": "/queue/123",
                "ack": "client",
                "my-header": "my-value",
            },
        )

    @unittest_run_loop
    async def test_can_unsubscribe(self):
        handler = Mock()
        subscription = Subscription(
            "/queue/123", 1, "client", {"my-header": "my-value"}, handler
        )

        await self.protocol.connect()
        self.protocol.unsubscribe(subscription)

        self._protocol.send_frame.assert_called_with(
            "UNSUBSCRIBE", {"id": 1, "destination": "/queue/123"}
        )

    @unittest_run_loop
    async def test_can_send(self):

        await self.protocol.connect()
        self.protocol.send({"content-length": 2}, "{}")

        self._protocol.send_frame.assert_called_with(
            "SEND", {"content-length": 2}, "{}"
        )
