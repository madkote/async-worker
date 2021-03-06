from http import HTTPStatus

from aiohttp import web
from asynctest import mock, TestCase

from asyncworker import App
from asyncworker.http import decorators
from asyncworker.http.decorators import parse_path
from asyncworker.testing import HttpClientContext


class HTTPDecoratorsTest(TestCase):
    async def setUp(self):
        self.app = App()

        @self.app.http.post(["/get_by_id/{_id}"])
        @parse_path
        async def get_by_id(_id: int):
            return web.json_response({"numero": _id})

        @self.app.http.post(["/param/{p1}/{p2}"])
        @parse_path
        async def path_multiple_params(p1: int, p2: int):
            return web.json_response({"p1": p1, "p2": p2})

    async def test_parse_one_path_param(self):
        async with HttpClientContext(self.app) as client:
            resp = await client.post("/get_by_id/42")
            data = await resp.json()
            self.assertEqual({"numero": 42}, data)

    async def test_parse_two_path_param(self):
        async with HttpClientContext(self.app) as client:
            resp = await client.post("/param/42/44")
            data = await resp.json()
            self.assertEqual({"p1": 42, "p2": 44}, data)

    async def test_raise_and_log_if_types_mismtach(self):
        """
        Se declararmos o argumento de um tipo inconpatível com o valor recebido
        lançamos uma exceção.
        Devemos gerar um logger.exception()
        """
        logger_mock_template = mock.CoroutineMock(
            exception=mock.CoroutineMock()
        )
        with mock.patch.object(
            decorators, "logger", logger_mock_template
        ) as logger_mock:
            async with HttpClientContext(self.app) as client:
                resp = await client.post("/get_by_id/abc")
                self.assertEqual(HTTPStatus.INTERNAL_SERVER_ERROR, resp.status)
                logger_mock.exception.assert_awaited_with(
                    {
                        "event": "incompatible-types-handler-arg",
                        "arg-type": int,
                        "arg-value": "abc",
                    }
                )
