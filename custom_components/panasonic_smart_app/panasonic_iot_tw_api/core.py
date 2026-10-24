from aiohttp import ClientSession, ClientError, ServerDisconnectedError, ClientResponseError
from http import HTTPStatus
from typing import Literal
import asyncio
import aiofiles
import datetime
import os
import json
import tempfile
import time
import logging
from .PanasonicAppliance import PanasonicAppliance

_LOGGER = logging.getLogger(__name__)

PANASMARTHOST = 'ems2.panasonic.com.tw'
USERAGENT = '(Mozilla/5.0 (iPhone; CPU iPhone OS 17_7_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1)'

UJ_COMMAND_LIST = {
	 "DeviceType":1,
	 "DeviceName":"冷氣機",
	 "ModelType":"UJ",
	 "ProtocalType":"SAA",
	 "ProtocalVersion":"4",
	 "Timestamp":"20250830142000",
	 "list":
      [
       {"CommandType":"0x00","CommandName":"電源","ParameterType":"enum","ParameterUnit":"","Parameters":[["停止",0],["運轉",1]]},
       {"CommandType":"0x01","CommandName":"運轉","ParameterType":"enum","ParameterUnit":"","Parameters":[['冷氣', 0], ['除濕', 1], ['清淨', 2], ['自動', 3], ['暖氣', 4]]},
	   {"CommandType":"0x03","CommandName":"溫度設定","ParameterType":"range","ParameterUnit":"度","Parameters":[["Min",16],["Max",30]]},
       {"CommandType":"0x02","CommandName":"風量設定","ParameterType":"rangeA","ParameterUnit":"","Parameters":[["Auto",0],["Min",1],["Max",5]]},
       {"CommandType":"0x08","CommandName":"nanoeX","ParameterType":"enum","ParameterUnit":"","Parameters":[["關閉",0],["開啟",1]]},
       {"CommandType":"0x0b","CommandName":"時間到開","ParameterType":"range","ParameterUnit":"分","Parameters":[["Min",0],["Max",1440]]},
       {"CommandType":"0x0c","CommandName":"時間到關","ParameterType":"range","ParameterUnit":"分","Parameters":[["Min",0],["Max",1440]]},
       {"CommandType":"0x0f","CommandName":"上下風向設定","ParameterType":"rangeA","ParameterUnit":"","Parameters":[["Auto",0],["Min",1],["Max",5]]},
       {"CommandType":"0x1b","CommandName":"ECONAVI","ParameterType":"enum","ParameterUnit":"","Parameters":[["關閉",0],["開啟",1]]},
       {"CommandType":"0x1e","CommandName":"操作提示音","ParameterType":"enum","ParameterUnit":"","Parameters":[["關閉",1],["開啟",0]]}
      ]
	}

DEHUMIDIFIER_COMMAND_LIST = {
    "DeviceType": 4,
    "DeviceName": "除濕機",
    "ModelType": "NNW-L",
    "ProtocalType": "SAANET",
    "ProtocalVersion": "4",
    "Timestamp": "20260509174000",
    "list": [
        {"CommandType": "0x00", "CommandName": "電源", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["停止", 0], ["運轉", 1]]},
        {"CommandType": "0x01", "CommandName": "功能選擇", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["連續除濕", 0], ["乾燥防霉（待機）", 1], ["送風模式", 3], ["衣物乾燥", 4], ["濕度設定", 6], ["智慧節能", 9], ["快速除濕", 10], ["靜音除濕", 11]]},
        {"CommandType": "0x04", "CommandName": "濕度設定", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["40%", 0], ["45%", 1], ["50%", 2], ["55%", 3], ["60%", 4], ["65%", 5], ["70%", 6]]},
        {"CommandType": "0x0E", "CommandName": "風量", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["自動", 0], ["弱", 1], ["中", 2], ["強", 3]]},
        {"CommandType": "0x09", "CommandName": "風向", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["固定", 0], ["自動", 3]]},
        {"CommandType": "0x18", "CommandName": "操作提示音", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["開啟", 0], ["關閉", 1]]},
        {"CommandType": "0x02", "CommandName": "時間到關", "ParameterType": "range", "ParameterUnit": "小時", "Parameters": [["Min", 0], ["Max", 12]]},
        {"CommandType": "0x55", "CommandName": "時間到開", "ParameterType": "range", "ParameterUnit": "小時", "Parameters": [["Min", 0], ["Max", 12]]},
        {"CommandType": "0x0D", "CommandName": "nanoeX", "ParameterType": "enum", "ParameterUnit": "", "Parameters": [["關閉", 0], ["開啟", 1]]},
    ],
}

HARDCODED_COMMAND_LISTS = {
    "UJ": UJ_COMMAND_LIST,
    "NNW-L": DEHUMIDIFIER_COMMAND_LIST,
}

FETCH_TIMEOUT = 20
# Seconds to wait after a failed login before the next login attempt.
LOGIN_RETRY_BACKOFF = 60
# Seconds to send no requests after the server replies HTTP 429.
RATE_LIMIT_COOLDOWN = 60
# Minimum seconds between the starts of two requests, to stay below the server rate limit.
REQUEST_SPACING = 1

LOGIN_ENDPOINT = '/api/Userlogin1'
DISCOVER_ENDPOINT = '/api/UserGetRegisteredGWList2'
DEVICE_INFO_ENDPOINT = '/api/DeviceGetInfo'
USER_INFO_ENDPOINT = '/api/UserGetInfo'
DEVICE_COMMAND_ENDPOINT = '/api/DeviceSetCommand'
POWER_LOG_ENDPOINT = '/api/PowerGetCTAreaLog'

COMMAND_FAIL = '\u7121\u6cd5\u900f\u904eCommandId\u53d6\u5f97Commmand' #無法透過CommandId取得Commmand
TOKEN_REJECTED_MESSAGES = (
    '\u6b64CPToken\u5df2\u7d93\u903e\u6642', #此CPToken已經逾時
    '\u7121\u6cd5\u4f9d\u64da\u60a8\u7684CPToken,auth\u53d6\u5f97\u76f8\u95dc\u8cc7\u6599', #無法依據您的CPToken,auth取得相關資料
)
# Fields that never appear in logs.
LOG_MASKED_KEYS = ('pw', 'memid', 'refreshtoken', 'auth')
# Fields that appear in logs with only their last 4 characters.
LOG_PARTIAL_KEYS = ('cptoken',)


def _redact(value):
    """Return a copy of value with credentials masked, for logging only."""
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            name = str(key).lower()
            if name in LOG_MASKED_KEYS:
                redacted[key] = '***'
            elif name in LOG_PARTIAL_KEYS and isinstance(item, str) and item:
                redacted[key] = '***' + item[-4:]
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


class core:
    def __init__(self, debug=False):
        self.debug = debug
        self.area_list = []
        self.valid_token = False
        self.login_retries = 0
        self.last_login_failure = None
        self.last_login_success = None
        self.rate_limited_until = None
        self.request_spacing = REQUEST_SPACING
        self.last_request_time = None
        self.request_lock = asyncio.Lock()
        self.login_lock = asyncio.Lock()
        self.CPToken = None
        self.cptoken_path = os.path.join(tempfile.gettempdir(), 'cptoken.json')
        self.session = None
        self.devices = []
        self.appliances = []
        self.lastcall = None
        self.exp = 0

    def _find_command_list(self, model_command_list, dev):
        """Find the best command list for a discovered device."""
        model_command_list = model_command_list or []
        dev_model_type = dev.get('ModelType')
        dev_device_type = dev.get('DeviceType')

        for model in model_command_list:
            if model.get('ModelType') == dev_model_type and model.get('JSON'):
                return model['JSON'][0]

        command_list = HARDCODED_COMMAND_LISTS.get(dev_model_type)
        if command_list is not None:
            _LOGGER.debug(
                "Using hardcoded command list for model type %s (%s).",
                dev_model_type,
                dev.get('Model'),
            )
            return command_list

        return None
    
    async def init(self, username, password, session=None, host=PANASMARTHOST, retries=3):
        """Async initialization to setup connection to Panasonic SMART server."""
        if self.debug:
            _LOGGER.debug('init()')
        self.username = username
        self.password = password
        self.host = host
        self.session = session
        self.headers = {
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'Expires': '-1',
            'auth': '',
            'CPToken': '',
            'Content-Type': 'application/json',
            'Charset': 'utf-8',
            'User-Agent': USERAGENT,
            'Host': self.host,
            'Connection': 'Keep-Alive'
        }
            
        if os.path.isfile(self.cptoken_path):
            _LOGGER.debug("PanasonicSAA4Api.init() load CPToken from file")
            with open(self.cptoken_path) as json_file:
                response_json = json.load(json_file)
                self.CPToken = response_json.get('CPToken')
                self.refreshToken = response_json.get('RefreshToken')
                self.expireTime = response_json.get('ExpireTime')
                self.MVersion = response_json.get('MVersion')
                self.exp = (datetime.datetime(
                                int(self.expireTime[0:4]),
                                int(self.expireTime[4:6]),
                                int(self.expireTime[6:8])) +
                            datetime.timedelta(
                                hours=int(self.expireTime[8:10]),
                                minutes=int(self.expireTime[10:12]),
                                seconds=int(self.expireTime[12:14])))
                self.lastcall = datetime.datetime.now()
                self.valid_token = True
                # check if CP token is expiring
                await self.check_access_token()
        else:
            _LOGGER.debug("init(): try to get a new token")
            self.lastcall = datetime.datetime.now()
            await self.get_access_token()
        
        appliance = await self.discover_devices()
        if appliance is not None: 
            return appliance
            
        if retries == 0:
            # Finish all retries and got nothing.
            _LOGGER.error(f'init() failed. {retries} retries to go.')
            return None
        return await self.init(username, password, session, host, retries=retries - 1)
    
    async def get_access_token(self):
        """Get access token with username and password registered in SMART app."""
        if self.debug: _LOGGER.debug('get_access_token()')
        if self.username == '' or self.password == '':
            _LOGGER.error("Please specify username and password.")
            self.valid_token = False
            return False
        
        headers = self.headers.copy()
        del headers['CPToken']
        del headers['auth']
        
        payload = {
            'AppToken': 'D8CBFF4C-2824-4342-B22D-189166FEF503',
            'MemId': self.username,
            'PW': self.password}
        
        response_json = await self.fetch(method='POST', endpoint=LOGIN_ENDPOINT, headers=headers, data=payload, retries=0)
        if not isinstance(response_json, dict) or not response_json.get('CPToken'):
            self.login_retries += 1
            self.last_login_failure = datetime.datetime.now()
            _LOGGER.error(
                "Failed to get access token (%s consecutive failures). "
                "Check username, password, and internet connection. Response: %s",
                self.login_retries, _redact(response_json))
            return False
            
        # Store token to file asynchronously
        async with aiofiles.open(self.cptoken_path, 'w') as outfile:
            await outfile.write(json.dumps(response_json))
        self.CPToken = response_json.get('CPToken')
        self.refreshToken = response_json.get('RefreshToken')
        self.expireTime = response_json.get('ExpireTime')
        self.MVersion = response_json.get('MVersion')
        self.exp = (datetime.datetime(
                        int(self.expireTime[0:4]),
                        int(self.expireTime[4:6]),
                        int(self.expireTime[6:8])) +
                    datetime.timedelta(
                        hours=int(self.expireTime[8:10]),
                        minutes=int(self.expireTime[10:12]),
                        seconds=int(self.expireTime[12:14])))
        self.login_retries = 0
        self.last_login_failure = None
        self.last_login_success = datetime.datetime.now()
        self.valid_token = True
        return True

    async def check_access_token(self):
        """Check if the access token is expired and need to be refresh."""
        async with self.login_lock:
            _LOGGER.debug(f'check_access_token() valid_token:{self.valid_token}, token expiry time:{self.exp}, lastcall:{self.lastcall} ')
            now = datetime.datetime.now()
            # CPToken expiring in 60 seconds or last call before 20mins
            if (not self.valid_token or (self.exp-now).total_seconds() < 60 or (now - self.lastcall).total_seconds() > 60*20):
                return await self._login_with_backoff()
            self.lastcall = now
            return True

    async def _renew_rejected_token(self, rejected_token):
        """Log in again after the server rejected rejected_token.
        Return True if a valid token is available.
        """
        async with self.login_lock:
            if self.valid_token and self.CPToken != rejected_token:
                # Another request already renewed the token.
                return True
            if (self.valid_token and self.last_login_success is not None
                    and (datetime.datetime.now() - self.last_login_success).total_seconds()
                    < LOGIN_RETRY_BACKOFF):
                # A fresh token was rejected; logging in again will not help.
                _LOGGER.warning("Skip login: the rejected CPToken is less than %s seconds old.",
                                LOGIN_RETRY_BACKOFF)
                return False
            self._remove_cached_token()
            return await self._login_with_backoff()

    async def _login_with_backoff(self):
        """Log in unless the last login failed recently. Call with login_lock held."""
        self.valid_token = False
        now = datetime.datetime.now()
        if self.last_login_failure is not None:
            elapsed = (now - self.last_login_failure).total_seconds()
            if elapsed < LOGIN_RETRY_BACKOFF:
                _LOGGER.warning(
                    "Skip login: last login failed %.0f seconds ago.", elapsed)
                return False
        self.lastcall = now
        return await self.get_access_token()

    def _remove_cached_token(self):
        """Remove the cached token file so a restart does not reuse a dead token."""
        try:
            os.remove(self.cptoken_path)
        except FileNotFoundError:
            pass
        except OSError as error:
            _LOGGER.warning("Unable to remove cached token %s: %s", self.cptoken_path, error)

    async def discover_devices(self, retries=3):
        """Discover devices registered in SMART app."""
        _LOGGER.debug('discover_devices()')
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('No valid token.')
            return None
        
        headers = self.headers.copy()
        headers['CPToken'] = self.CPToken
        del headers['auth']

        response_json = await self.fetch(method='GET', endpoint=DISCOVER_ENDPOINT, headers=headers, retries=retries)
        #_LOGGER.debug('discover_devices: response_json:%s', json.dumps(response_json))
        if response_json is not None and isinstance(response_json, dict) and response_json.get('State')=='success':
            gwlist = response_json.get('GwList')
            model_command_list = response_json.get('CommandList')
            #if(self.debug): _LOGGER.debug('discover_devices: gwlist:%s, command_list:%s', json.dumps(gwlist), json.dumps(model_command_list))
            if len(gwlist) == 0:
                _LOGGER.error("Please add gateways to your account first.")
                return None
            for gw in gwlist:
                for dev in gw['Devices']:
                    dev['GWID'] = gw['GWID']
                    dev['auth'] = gw['Auth']
                    dev['AreaID'] = gw['AreaID']
                    dev['NickName'] = gw['NickName']
                    dev['Model'] = gw['Model']
                    dev['DeviceType'] = gw['DeviceType']
                    dev['ModelType'] = gw['ModelType']
                    dev['CommandList'] = self._find_command_list(model_command_list, dev)
                    if dev['CommandList'] is None:
                        _LOGGER.warning(
                            "Skipping unsupported device %s (%s, model type %s) because no command list is available.",
                            dev.get('NickName'),
                            dev.get('Model'),
                            dev.get('ModelType'),
                        )
                        continue
                    self.devices.append(dev)
                    appliance = PanasonicAppliance(dev, self, self.debug)
                    self.appliances.append(appliance)
                    if dev['AreaID'] not in self.area_list:
                        self.area_list.append(dev['AreaID'])
            _LOGGER.debug(
                "devices: %s",
                [
                    {
                        "NickName": device.get("NickName"),
                        "DeviceType": device.get("DeviceType"),
                        "ModelType": device.get("ModelType"),
                        "Model": device.get("Model"),
                    }
                    for device in self.devices
                ],
            )
            return self.appliances
        return None

    async def device_status(self, device, commands, retries=3):
        """Get device status."""
        _LOGGER.debug('device_status()')
        token_valid = await self.check_access_token()
        if not token_valid or commands is None or len(commands) == 0:
            _LOGGER.error('No valid token or empty command list.')
            return None
        
        headers = self.headers.copy()
        headers['CPToken'] = self.CPToken
        headers['auth'] = device['auth']

        command_list = []
        for command in commands:
            command_list.append({'CommandType': '{0:#0{1}x}'.format(command, 4)})

        payload = [{'CommandTypes': command_list, 'DeviceID': int(device['DeviceID'])}]

        response_json = await self.fetch(method='POST', endpoint=DEVICE_INFO_ENDPOINT, headers=headers, data=payload, retries=0)
        if response_json is not None and isinstance(response_json, dict):
            if response_json.get('status')=='success':
                return response_json.get('devices')[0].get('Info')
            elif response_json.get('State')=='fail' and response_json.get('StateMsg') == COMMAND_FAIL:
                _LOGGER.debug(f'device_status() Server expectation error; command failed, return without retry')       
                return None    
        if retries == 0:
            # Finish all retries and got nothing.
            _LOGGER.error(f'device_status() failed. {retries} retries to go.')
            return None
        return await self.device_status(device, commands, retries=retries - 1)

    async def device_control(self, device, command_type, value, retries=3):
        """Send command to control the device."""
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('device_control() No valid token.')
            return False

        headers = self.headers.copy()
        headers['CPToken'] = self.CPToken
        headers['auth'] = device['auth']

        endpoint = (DEVICE_COMMAND_ENDPOINT+
                    '?DeviceID=' + str(device['DeviceID']) +
                    '&commandType={0:#0{1}x}'.format(command_type+0x80, 4) +
                    '&Value=' + str(value))
        if self.debug:
            _LOGGER.debug('device_control() command url to send:'+ endpoint)
        response_json = await self.fetch(method='GET', endpoint=endpoint, headers=headers, data=None, retries=retries)
        if not isinstance(response_json, dict):
            _LOGGER.error('device_control() got no response for %s.', endpoint)
            return False
        return response_json.get('status') == 'success'

    async def get_power_log(
            self, appliance, unit='hour', from_date=None, max_num=24,
            retries=3):
        """Get area power log buckets for an appliance."""
        _LOGGER.debug("get_power_log()")
        if unit not in ('hour', 'day', 'month'):
            raise ValueError(f"Unsupported power log unit: {unit}")
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('No valid token.')
            return None
        headers = self.headers.copy()
        headers['CPToken']=self.CPToken
        headers['auth'] = appliance.auth

        if from_date is None:
            from_date = datetime.date.today()
        if isinstance(from_date, datetime.datetime):
            from_date = from_date.date()
        if isinstance(from_date, datetime.date):
            from_value = from_date.strftime('%Y/%m/%d')
        else:
            from_value = str(from_date)

        area_id = appliance.get_area_id()
        try:
            area_id = int(area_id)
        except (TypeError, ValueError):
            pass

        payload = {
            'gw_id': appliance.get_gwid(),
            'area_ids': [area_id],
            'from': from_value,
            'unit': unit,
            'max_num': max_num,
        }
        _LOGGER.debug(
            "get_power_log() endpoint=%s unit=%s from=%s max_num=%s area_ids=%s",
            POWER_LOG_ENDPOINT, unit, from_value, max_num, [area_id])
        return await self.fetch(
            method='POST',
            endpoint=POWER_LOG_ENDPOINT,
            headers=headers,
            data=payload,
            retries=retries,
        )

    def _rate_limited(self):
        """Return True while the HTTP 429 cooldown is active."""
        return (self.rate_limited_until is not None
                and datetime.datetime.now() < self.rate_limited_until)

    async def _wait_for_request_slot(self):
        """Wait until request_spacing seconds passed since the last request start.
        Return False, without waiting, while the HTTP 429 cooldown is active.
        """
        async with self.request_lock:
            if self._rate_limited():
                return False
            if self.last_request_time is not None:
                wait = self.request_spacing - (time.monotonic() - self.last_request_time)
                if wait > 0:
                    await asyncio.sleep(wait)
            # A request sent before the wait can return HTTP 429 during the wait.
            if self._rate_limited():
                return False
            self.last_request_time = time.monotonic()
            return True

    async def fetch(self, method: Literal['GET', 'POST'], endpoint, headers, data=None, retries=3,
                    retry_on_token_rejected=True):
        """Generic fetch function to handle device control and logs."""
        if not await self._wait_for_request_slot():
            _LOGGER.debug(
                "fetch() skip %s: rate limited until %s.",
                endpoint, self.rate_limited_until.strftime('%H:%M:%S'))
            return None
        try:
            if self.session is None or self.session.closed:
                _LOGGER.debug(f'fetch() session is not valid, create a new client session')
                self.session = ClientSession()
            
            url = f'https://{self.host}{endpoint}'
            json_data = None
            if data is not None: 
                json_data = json.dumps(data)
            
            _LOGGER.debug(f'fetch() retries:{retries}, url:{url}; header:{_redact(headers)}; data:{_redact(data)}')
            response = await self.session.request(method=method, url=url, headers=headers, data=json_data, timeout=FETCH_TIMEOUT)
            
        except (asyncio.TimeoutError, ClientError, ServerDisconnectedError, ClientResponseError) as error:
            _LOGGER.warning(f'fetch() error: {type(error).__name__}, {retries} retries to go.')
            if retries == 0:
                return None
            return await self.fetch(method, endpoint, headers, data, retries=retries - 1)
        except Exception as error:
            _LOGGER.error(f'fetch() Unexpected exception: {type(error).__name__}, {error.args}')
            if retries == 0:
                return None
            return await self.fetch(method, endpoint, headers, data, retries=retries - 1)

        if response is not None:
            if response.status == HTTPStatus.OK:
                response_json = await response.json()
                if response_json is None:
                    _LOGGER.warning(
                        "fetch() endpoint %s returned empty JSON response.",
                        endpoint)
                return response_json
            elif response.status == HTTPStatus.TOO_MANY_REQUESTS:
                # An immediate retry makes the rate limit worse, so pause all requests.
                self.rate_limited_until = (
                    datetime.datetime.now()
                    + datetime.timedelta(seconds=RATE_LIMIT_COOLDOWN))
                _LOGGER.error(
                    "fetch() endpoint %s: server rate limit (HTTP 429). "
                    "No requests for %s seconds.", endpoint, RATE_LIMIT_COOLDOWN)
                return None
            elif response.status == HTTPStatus.EXPECTATION_FAILED:
                try:
                    response_json = await response.json()
                except Exception:
                    response_json = None
                rejected_token = headers.get('CPToken')
                if rejected_token and (
                        not isinstance(response_json, dict)
                        or response_json.get('StateMsg') in TOKEN_REJECTED_MESSAGES):
                    # The server rejected the CPToken before our expiry check
                    # noticed. Log in again and retry this request once.
                    _LOGGER.warning(
                        "fetch() endpoint %s rejected the CPToken: %s",
                        endpoint, _redact(response_json))
                    if (retry_on_token_rejected
                            and await self._renew_rejected_token(rejected_token)):
                        headers = headers.copy()
                        headers['CPToken'] = self.CPToken
                        return await self.fetch(
                            method, endpoint, headers, data, retries=0,
                            retry_on_token_rejected=False)
                    return None
                if response_json is None:
                    _LOGGER.error('fetch() server expectation failed. Login error')
                return response_json
            else:
                _LOGGER.warning(
                    "fetch() endpoint %s returned HTTP status %s.",
                    endpoint, response.status)
        
        if retries == 0:
            # Finish all retries and got nothing.
            _LOGGER.error(f'fetch() failed. {retries} retries to go.')
            return None
        return await self.fetch(method, endpoint, headers, data, retries=retries - 1)
