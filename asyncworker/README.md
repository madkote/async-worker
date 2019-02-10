
[![Build Status](https://travis-ci.org/B2W-BIT/easyqueue.svg?branch=master)](https://travis-ci.org/B2W-BIT/easyqueue)
[![codecov](https://codecov.io/gh/B2W-BIT/easyqueue/branch/master/graph/badge.svg)](https://codecov.io/gh/B2W-BIT/easyqueue)
[![PyPI](https://img.shields.io/pypi/v/easyqueue.svg)](http://pypi.python.org/pypi/easyqueue)
[![PyPI - Python Version](https://img.shields.io/pypi/pyversions/easyqueue.svg)](http://pypi.python.org/pypi/easyqueue)

# EasyQueue

An easy way to asynchronously handle AMQP queue consumption.

# Installation

`pip install easyqueue` 

# Run tests
Install the test dependencies
`pip install pipenv && pipenv install --dev`

*Simple test run:*  
`py.test`

*Show coverage*  
`py.test --cov=easyqueue`

# AsyncJsonQueue

Class used for asynchronously connecting and consuming
 `amqp` queues. `AsyncJsonQueue` uses the delegation pattern
 to provide abstractions for queue communication.

 ## Hello World - the simplest code that does something

``` python
import asyncio
from easyqueue import AsyncJsonQueue, AsyncQueueConsumerDelegate
from easyqueue.message import AMQPMessage


class MyConsumer(AsyncQueueConsumerDelegate):
    queue_name = 'words'

    def __init__(self):
        self.queue = AsyncJsonQueue(
            host='localhost',
            username='guest',
            password='guest',
            delegate=self
        )

    async def on_before_start_consumption(self, queue_name: str,
                                          queue: AsyncJsonQueue):
        print("I'm called when queue consumption starts !")

    async def on_message_handle_error(self,
                                      handler_error: Exception,
                                      **kwargs):
        print("I'm called if an unhandled exception is raised on"
              "on_queue_message")

    async def on_consumption_start(self,
                                   consumer_tag: str,
                                   queue: 'AsyncJsonQueue'):
        print("Once consumption started, im called with the consumer tag.")

    async def on_queue_message(self, msg: AMQPMessage[dict]):
        """
        Called every time that a new, valid and deserialized message
        is ready to be handled.
        """
        print(msg.deserialized_data)  # do something with
        await self.queue.ack(msg)  # dont forget to ack =)


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    consumer = MyConsumer()
    loop.create_task(consumer.start())
    loop.run_forever()

```

# Guia de migração 2.0.0 -> 3.x.x

A partir da versão `3.0.0` a classe `AsyncQueue` foi renomeada para `AsyncJsonQueue`. 

# Guia de migração 1.2.x -> 2.0.0

O método `AsyncQueue.put` não aceita mais `body` como parâmetro de corpo da mensagem  
e foi substituido pelos parâmetros `data` e `serialized_data`. 
* `data` funciona da mesma forma 
que body funcionava, esperando qualquer dado serializável em json 
* `serialized_data` existe para publicar a mensagem sem passar pela etapa de serialização

# Guia de migração 1.1.0 -> 1.2.x

As classes `AsyncQueue` e `AsyncQueueConsumerDelegate` não estão mais no módulo
`async.py` que em python 3.7 é uma palavra reservada e foram movidas para `async_queue.py`.
Ambas as classes estão disponíveis no nível do módulo do easyqueue o que significa
que os imports devem mudar de: 
`from easyqueue.async import AsyncQueue, AsyncQueueConsumerDelegate` 
para:
`from easyqueue import AsyncQueue, AsyncQueueConsumerDelegate`
