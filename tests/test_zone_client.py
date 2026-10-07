"""Client wiring checks with HTTP dependency stubbed; no network requests."""
import importlib.util
import os
import sys
import types
import unittest
from unittest.mock import AsyncMock, patch
from test_zone_open import COMPONENT, PACKAGE, VARIANT, payload

# Only ClientSession is needed by evaluated type annotations; no HTTP is used.
with patch.dict(sys.modules, {'aiohttp': types.SimpleNamespace(ClientSession=object)}):
    spec = importlib.util.spec_from_file_location(
        PACKAGE + '.base', os.environ.get('COMBIVOX_TEST_CLIENT', COMPONENT / 'base.py'))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
Client = module.CombivoxWebClient


class ClientZoneTests(unittest.IsolatedAsyncioTestCase):
    def client(self):
        client = Client('192.0.2.1', 'unused-test-code')
        client._zones_config = [{'zone_id': 18, 'zone_name': 'Test'}]
        client._zone_ids = [18]
        return client

    async def test_identification_precedes_first_status(self):
        client = self.client()
        events = []
        client._authenticate_and_download_config = AsyncMock(return_value=True)
        async def identify():
            events.append('identify')
            client._device_info = {'variant': VARIANT}
        async def initial():
            events.append('status')
            self.assertTrue(client._parse_status_response(payload(writes=[(114,'02')]))['zones'][18]['open'])
        client._fetch_device_info = identify
        client._fetch_initial_status = initial
        self.assertTrue(await client.connect())
        self.assertEqual(events, ['identify', 'status'])

    async def test_missing_identification_keeps_legacy_behavior(self):
        client = self.client()
        client._authenticate_and_download_config = AsyncMock(return_value=True)
        client._fetch_device_info = AsyncMock(side_effect=RuntimeError('test failure'))
        client._fetch_initial_status = AsyncMock()
        with self.assertLogs(PACKAGE + '.base', level='WARNING'):
            self.assertTrue(await client.connect())
        client._fetch_initial_status.assert_awaited_once()
        self.assertTrue(client._parse_status_response(payload(writes=[(110,'02')]))['zones'][18]['open'])
        self.assertFalse(client._parse_status_response(payload(writes=[(114,'02')]))['zones'][18]['open'])
