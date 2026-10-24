"""Regression test for Panasonic CPToken recovery in panasonic_iot_tw_api.core.

Purpose:
    Check that the API client recovers when the Panasonic server rejects the
    CPToken or when login fails. The test uses a fake HTTP session, so it does
    not contact the Panasonic server. It stubs aiohttp and aiofiles, so it
    needs no extra packages.

Use:
    python3 scripts/test_token_recovery.py

    The script prints one line per scenario and exits with status 1 if a
    scenario fails.
"""
import asyncio
import datetime
import json
import logging
import os
import sys
import tempfile
import time
import types

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO_ROOT, 'custom_components', 'panasonic_smart_app'))


def install_stubs():
    """Install minimal aiohttp and aiofiles modules for core.py imports."""
    aiohttp = types.ModuleType('aiohttp')

    class ClientError(Exception):
        pass

    class ServerDisconnectedError(ClientError):
        pass

    class ClientResponseError(ClientError):
        pass

    class ClientSession:
        closed = False

    aiohttp.ClientError = ClientError
    aiohttp.ServerDisconnectedError = ServerDisconnectedError
    aiohttp.ClientResponseError = ClientResponseError
    aiohttp.ClientSession = ClientSession
    sys.modules['aiohttp'] = aiohttp

    aiofiles = types.ModuleType('aiofiles')

    class AsyncFile:
        def __init__(self, path, mode):
            self._file = open(path, mode)

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            self._file.close()

        async def write(self, text):
            self._file.write(text)

    aiofiles.open = AsyncFile
    sys.modules['aiofiles'] = aiofiles


install_stubs()
import importlib  # noqa: E402

# The package __init__ exports a class named core, so load the module itself.
core_module = importlib.import_module('panasonic_iot_tw_api.core')

TOKEN_EXPIRED_MSG = core_module.TOKEN_REJECTED_MESSAGES[0]
FAR_FUTURE = '20991231235959'


class FakeResponse:
    def __init__(self, status, body):
        self.status = status
        self._body = body

    async def json(self):
        if isinstance(self._body, str):
            raise ValueError('not JSON')
        return self._body


class FakeSession:
    """Route requests to a handler and record each endpoint called."""

    closed = False

    def __init__(self, handler):
        self.handler = handler
        self.calls = []
        self.times = []

    async def request(self, method, url, headers, data, timeout):
        endpoint = url.split('ems2.panasonic.com.tw', 1)[1].split('?', 1)[0]
        self.calls.append((endpoint, headers.get('CPToken')))
        self.times.append(time.monotonic())
        await asyncio.sleep(0)
        return self.handler(endpoint, headers)

    def logins(self):
        return sum(1 for endpoint, _ in self.calls if endpoint == core_module.LOGIN_ENDPOINT)


def login_ok(token):
    return FakeResponse(200, {
        'CPToken': token, 'RefreshToken': 'R', 'ExpireTime': FAR_FUTURE, 'MVersion': '1'})


def status_ok():
    return FakeResponse(200, {
        'status': 'success',
        'devices': [{'Info': [{'CommandType': '0x00', 'status': '1'}]}]})


def make_core(handler, tmpdir, token='OLD'):
    api = core_module.core()
    api.cptoken_path = os.path.join(tmpdir, 'cptoken.json')
    api.username = 'user'
    api.password = 'pw'
    api.host = 'ems2.panasonic.com.tw'
    api.headers = {'auth': '', 'CPToken': '', 'Content-Type': 'application/json'}
    api.session = FakeSession(handler)
    api.request_spacing = 0  # Keep the other scenarios fast.
    api.CPToken = token
    api.valid_token = True
    api.exp = datetime.datetime(2099, 12, 31)
    api.lastcall = datetime.datetime.now()
    with open(api.cptoken_path, 'w') as cache:
        json.dump({'CPToken': token}, cache)
    return api


DEVICE = {'auth': 'A', 'DeviceID': 1}


async def scenario_rejected_token_relogin(tmpdir):
    """A 417 token-expired reply triggers one login and a successful retry."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW')
        if headers.get('CPToken') == 'NEW':
            return status_ok()
        return FakeResponse(417, {'State': 'fail', 'StateMsg': TOKEN_EXPIRED_MSG})

    api = make_core(handler, tmpdir)
    info = await api.device_status(DEVICE, [0])
    with open(api.cptoken_path) as cache:
        cached = json.load(cache)['CPToken']
    assert info is not None, 'status was not returned after login'
    assert api.CPToken == 'NEW'
    assert api.session.logins() == 1, api.session.calls
    assert cached == 'NEW', 'cache file still holds the rejected token'


async def scenario_non_json_417_relogin(tmpdir):
    """A 417 reply that is not JSON also triggers a login."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW')
        if headers.get('CPToken') == 'NEW':
            return status_ok()
        return FakeResponse(417, 'html error page')

    api = make_core(handler, tmpdir)
    assert await api.device_status(DEVICE, [0]) is not None
    assert api.session.logins() == 1


async def scenario_no_permanent_lockout(tmpdir):
    """Five failed logins do not stop a later login attempt."""
    state = {'login_ok': False}

    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW') if state['login_ok'] else FakeResponse(500, {})
        return status_ok()

    api = make_core(handler, tmpdir)
    api.valid_token = False
    for _ in range(5):
        api.last_login_failure = None  # Simulate the backoff period passing.
        assert await api.check_access_token() is False
    assert api.login_retries == 5
    state['login_ok'] = True
    api.last_login_failure -= datetime.timedelta(seconds=core_module.LOGIN_RETRY_BACKOFF + 1)
    assert await api.check_access_token() is True
    assert api.login_retries == 0


async def scenario_backoff_limits_logins(tmpdir):
    """Calls inside the backoff period after a failed login do not log in."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return FakeResponse(500, {})
        return status_ok()

    api = make_core(handler, tmpdir)
    api.valid_token = False
    for _ in range(4):
        await api.device_status(DEVICE, [0], retries=0)
        await api.get_power_log(types.SimpleNamespace(
            auth='A', get_gwid=lambda: 'G', get_area_id=lambda: 0))
    assert api.session.logins() == 1, api.session.calls


async def scenario_concurrent_rejection_single_login(tmpdir):
    """Two requests rejected at the same time cause only one login."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW')
        if headers.get('CPToken') == 'NEW':
            return status_ok()
        return FakeResponse(417, {'State': 'fail', 'StateMsg': TOKEN_EXPIRED_MSG})

    api = make_core(handler, tmpdir)
    results = await asyncio.gather(
        api.device_status(DEVICE, [0]), api.device_status(DEVICE, [0]))
    assert all(result is not None for result in results)
    assert api.session.logins() == 1, api.session.calls


async def scenario_fresh_token_rejected_no_loop(tmpdir):
    """A rejection of a token from a recent login does not start another login."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW')
        return FakeResponse(417, {'State': 'fail', 'StateMsg': TOKEN_EXPIRED_MSG})

    api = make_core(handler, tmpdir)
    assert await api.device_status(DEVICE, [0]) is None
    assert api.session.logins() == 1, api.session.calls


async def scenario_command_fail_no_login(tmpdir):
    """A 417 command error is returned to the caller without a login."""
    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return login_ok('NEW')
        return FakeResponse(417, {'State': 'fail', 'StateMsg': core_module.COMMAND_FAIL})

    api = make_core(handler, tmpdir)
    assert await api.device_status(DEVICE, [0]) is None
    assert api.session.logins() == 0
    assert api.CPToken == 'OLD'


async def scenario_device_control_no_response(tmpdir):
    """device_control returns False when the server gives no response."""
    def handler(endpoint, headers):
        return FakeResponse(500, {})

    api = make_core(handler, tmpdir)
    assert await api.device_control(DEVICE, 0, 1, retries=0) is False


async def scenario_logs_hide_credentials(tmpdir):
    """Debug logs of a login and a status request contain no credentials."""
    secrets = ['0912345678', 'S3cretPass!', 'NEW-TOKEN-ABCDEFGH', 'REFRESH-SECRET', 'DEVICE-AUTH-XYZ']

    def handler(endpoint, headers):
        if endpoint == core_module.LOGIN_ENDPOINT:
            return FakeResponse(200, {
                'CPToken': secrets[2], 'RefreshToken': secrets[3],
                'ExpireTime': FAR_FUTURE, 'MVersion': '1'})
        return status_ok()

    class Capture(logging.Handler):
        def __init__(self):
            super().__init__(logging.DEBUG)
            self.messages = []

        def emit(self, record):
            self.messages.append(record.getMessage())

    capture = Capture()
    logger = logging.getLogger(core_module.__name__)
    logger.addHandler(capture)
    logger.setLevel(logging.DEBUG)
    try:
        api = make_core(handler, tmpdir)
        api.username = secrets[0]
        api.password = secrets[1]
        api.valid_token = False
        assert await api.device_status({'auth': secrets[4], 'DeviceID': 1}, [0]) is not None
    finally:
        logger.removeHandler(capture)
    text = '\n'.join(capture.messages)
    assert 'fetch()' in text, 'no fetch() debug line was captured'
    leaked = [secret for secret in secrets if secret in text]
    assert not leaked, f'credentials in log: {leaked}'


async def scenario_rate_limit_pauses_requests(tmpdir):
    """HTTP 429 sends no retry, and requests stop until the cooldown ends."""
    def handler(endpoint, headers):
        return FakeResponse(429, {})

    api = make_core(handler, tmpdir)
    assert await api.device_status(DEVICE, [0]) is None
    assert len(api.session.calls) == 1, api.session.calls
    assert await api.fetch('GET', core_module.DISCOVER_ENDPOINT, {}, retries=3) is None
    assert len(api.session.calls) == 1, 'a request was sent during the cooldown'
    api.session.handler = lambda endpoint, headers: status_ok()
    api.rate_limited_until -= datetime.timedelta(seconds=core_module.RATE_LIMIT_COOLDOWN + 1)
    assert await api.device_status(DEVICE, [0]) is not None
    assert len(api.session.calls) == 2


async def scenario_requests_are_spaced(tmpdir):
    """Concurrent requests start at least request_spacing seconds apart."""
    spacing = 0.05

    def handler(endpoint, headers):
        return status_ok()

    api = make_core(handler, tmpdir)
    api.request_spacing = spacing
    results = await asyncio.gather(*(api.device_status(DEVICE, [0]) for _ in range(4)))
    assert all(result is not None for result in results)
    gaps = [later - earlier for earlier, later in zip(api.session.times, api.session.times[1:])]
    assert len(gaps) == 3 and min(gaps) >= spacing * 0.9, gaps


SCENARIOS = [
    scenario_rejected_token_relogin,
    scenario_non_json_417_relogin,
    scenario_no_permanent_lockout,
    scenario_backoff_limits_logins,
    scenario_concurrent_rejection_single_login,
    scenario_fresh_token_rejected_no_loop,
    scenario_command_fail_no_login,
    scenario_device_control_no_response,
    scenario_logs_hide_credentials,
    scenario_rate_limit_pauses_requests,
    scenario_requests_are_spaced,
]


def main():
    failures = 0
    for scenario in SCENARIOS:
        with tempfile.TemporaryDirectory() as tmpdir:
            try:
                asyncio.run(scenario(tmpdir))
                print(f'PASS {scenario.__name__}')
            except AssertionError as error:
                failures += 1
                print(f'FAIL {scenario.__name__}: {error}')
    sys.exit(1 if failures else 0)


if __name__ == '__main__':
    main()
