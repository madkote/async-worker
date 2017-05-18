import abc
import aioamqp
import asyncio
from typing import Any, Dict
from json.decoder import JSONDecodeError
from easyqueue.queue import BaseJsonQueue
from easyqueue.exceptions import UndecodableMessageException, \
    InvalidMessageSizeException, MessageError


class AsyncQueueConsumerDelegate(metaclass=abc.ABCMeta):
    @property
    @abc.abstractmethod
    def loop(self) -> asyncio.BaseEventLoop:
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def queue(self) -> 'AsyncQueue':
        """ AsyncQueue instance to be used as a connection provider """
        raise NotImplementedError

    @property
    @abc.abstractmethod
    def queue_name(self) -> str:
        """ Name of the input queue to consume """
        raise NotImplementedError

    async def _consume(self):
        """ Coroutine that starts the connection and the queue consumption """
        await self.queue.connect()
        await self.queue.consume(queue_name=self.queue_name)

    async def on_before_start_consumption(self, queue_name, queue):
        """
        Coroutine called before queue consumption starts. May be overwritten to
        implement further custom initialization.
        
        :param queue_name: Queue name that will be consumed
        :type queue_name: str
        :param queue: AsynQueue instanced 
        :type queue: AsyncQueue
        """
        pass

    @abc.abstractmethod
    async def on_queue_message(self, content, delivery_tag, queue):
        """
        Callback called every time that a new, valid and deserialized message 
        is ready to be handled.
        
        :param delivery_tag: delivery_tag of the consumed message 
        :type delivery_tag: int
        :param content: parsed message body
        :type content: dict
        :type queue: AsyncQueue
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def on_queue_error(self, body, delivery_tag, error, queue):
        """
        Callback called every time that an error occurred during the validation
        or deserialization stage. 
        
        :param body: unparsed, raw message content
        :type body: Any
        :param delivery_tag: delivery_tag of the consumed message 
        :type delivery_tag: int
        :param error: THe error that caused the callback to be called
        :type error: MessageError
        :type queue: AsyncQueue
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def on_message_handle_error(self, handler_error: Exception, **kwargs):
        """
        Callback called when an uncaught exception was raised during message 
        handling stage.
        
        :param handler_error: The exception that triggered 
        :param kwargs: arguments used to call the coroutine that handled 
        the message
        :return: 
        """
        raise NotImplementedError

    @abc.abstractmethod
    async def on_connection_error(self, exception: Exception):
        """
        Called when the connection fails
        """
        raise NotImplementedError

    def run(self):
        consume_task = self.loop.create_task(self._consume())
        self.loop.run_forever()
        return consume_task

    def run_until_complete(self):
        self.loop.run_until_complete(self._consume())


class AsyncQueue(BaseJsonQueue):
    def __init__(self,
                 host: str,
                 username: str,
                 password: str,
                 delegate: AsyncQueueConsumerDelegate,
                 virtual_host: str = '/',
                 heartbeat: int = 60,
                 prefetch_count: int=100,
                 max_message_length=0,
                 loop=None):

        super().__init__(host, username, password, virtual_host, heartbeat)

        self.delegate = delegate
        self.loop = loop or asyncio.get_event_loop()
        self.prefetch_count = prefetch_count

        if max_message_length < 0:
            raise ValueError("max_message_length must be a positive integer")

        self.max_message_length = max_message_length

        self._protocol = None  # type: aioamqp.protocol.AmqpProtocol
        self._transport = None  # type: asyncio.BaseTransport
        self._channel = None  # type: aioamqp.channel.Channel

    @property
    def connection_parameters(self):
        return {
            'host': self.host,
            'login': self.username,
            'password': self.password,
            'virtualhost': self.virtual_host,
            'loop': self.loop,
            'on_error': self.delegate.on_connection_error
        }

    @property
    def is_connected(self):
        # todo: This may not be enough
        return self._channel and self._channel.is_open

    async def connect(self):
        conn = await aioamqp.connect(**self.connection_parameters)
        self._transport, self._protocol = conn
        self._channel = await self._protocol.channel()

    async def close(self):
        await self._protocol.close()
        self._transport.close()

    async def ack(self, delivery_tag: int):
        return await self._channel.basic_client_ack(delivery_tag)

    async def reject(self, delivery_tag: int, requeue=False):
        return await self._channel.basic_reject(delivery_tag=delivery_tag,
                                                requeue=requeue)

    async def put(self, body: any, routing_key: str, exchange: str = '', priority: int = 0):
        if priority:
            raise NotImplementedError
        payload = self.serialize(body)
        return await self._channel.publish(payload=payload,
                                           exchange_name=exchange,
                                           routing_key=routing_key)

    def _parse_message(self, body) -> Dict[str, Any]:
        if self.max_message_length:
            if len(body) > self.max_message_length:
                raise InvalidMessageSizeException(body)
        try:
            return self.deserialize(body)
        except TypeError as e:
            return self._parse_message(body.decode())
        except JSONDecodeError as e:
            raise UndecodableMessageException('"{body}" can\'t be decoded as JSON'
                                              .format(body=body))

    async def _handle_callback(self, callback, **kwargs):
        """
        Chains the callback coroutine into a try/except and calls 
        `on_message_handle_error` in case of failure, avoiding unhandled 
        exceptions.
         
        :param callback: 
        :param kwargs: 
        :return: 
        """
        try:
            return await callback(**kwargs)
        except Exception as e:
            return await self.delegate.on_message_handle_error(handler_error=e,
                                                               **kwargs)

    async def _handle_message(self, channel, body, envelope, properties):
        """
        :rtype: asyncio.Task
        """
        tag = envelope.delivery_tag
        try:
            content = self._parse_message(body)
        except MessageError as e:
            callback = self._handle_callback(self.delegate.on_queue_error,
                                             body=body,
                                             delivery_tag=tag,
                                             error=e,
                                             queue=self)
        else:
            callback = self._handle_callback(self.delegate.on_queue_message,
                                             content=content,
                                             delivery_tag=tag,
                                             queue=self)
        return self.loop.create_task(callback)

    async def consume(self, queue_name: str, consumer_name: str='') -> str:
        """
        :param queue_name: queue to consume
        :param consumer_name: Name to be used as a consumer identifier.
        :return: The consumer tag. Useful for cancelling/stopping consumption
        """
        # todo: Implement a consumer tag generator
        await self.delegate.on_before_start_consumption(queue_name, queue=self)

        if self._channel is None:
            raise ConnectionError("Queue isn't connected. "
                                  "Did you forgot to wait for `connect()`?")

        await self._channel.basic_qos(prefetch_count=self.prefetch_count,
                                      prefetch_size=0,
                                      connection_global=False)
        tag = await self._channel.basic_consume(callback=self._handle_message,
                                                consumer_tag=consumer_name,
                                                queue_name=queue_name)
        return tag['consumer_tag']

    async def stop_consumer(self, consumer_tag: str):
        if self._channel is None:
            raise ConnectionError("Queue isn't connected. "
                                  "Did you forgot to wait for `connect()`?")

        return await self._channel.basic_cancel(consumer_tag)
