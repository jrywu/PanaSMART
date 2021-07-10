"""Python module to control Panasonic SMART applicances supporting SAAnet 4 protocol."""
import json
import logging
from aiohttp import ClientSession
from aiohttp import ServerDisconnectedError, ClientResponseError
import asyncio
from async_timeout import timeout
import datetime
import os
import tempfile

PANASMARTHOST = 'ems2.panasonic.com.tw'
USERAGENT = ('Dalvik/2.1.0 '
             '(Linux; U; Android 8.0.0 HTC_U-3u Build/OPR6.170623.013)')

_LOGGER = logging.getLogger(__name__)


class PanasonicSAA4Api:
    """Panasonic SMART applicances control interface with SAAnet 4 protocol."""

    def __init__(self, debug=False):
        """Initialize the interface."""
        self.appliances = None
        self.area_list = []
        self.debug = debug
        self.valid_token = False
        self.login_retries = 0
        self.cptoken_path = os.path.join(tempfile.gettempdir(), 'cptoken.json')

    async def init(self, username, password, session=None, host=PANASMARTHOST):
        """Async intialization to setup connection to Panasonic SMART server."""
        if(self.debug):
            print('init()')
        self.session = session
        self.username = username
        self.password = password
        self.host = host

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
            _LOGGER.info("PanasonicSAA4Api.init() get a new token")
            self.lastcall = datetime.datetime.now()
            await self.get_access_token()
        return await self.discover_devices()

    async def get_access_token(self, retries=3):
        """Get access token with username and password registered in SMART app."""
        if self.login_retries > 5:
            _LOGGER.error("To many login retries. Abort now.")
            return False
        try:
            with timeout(30):
                if self.session and not self.session.closed:
                    return await self._get_access_token()
                else:
                    async with ClientSession() as self.session:
                        return await self._get_access_token()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                'Timeout for retrieving access token. '
                '' + str(retries) + ' retries to go.    ')
        except ServerDisconnectedError as error:
            _LOGGER.warning(
                'ServerDisconnectedError: %d retries to go.', retries)
        except asyncio.TimeoutError:
            _LOGGER.error(
                    'asyncio.TimeoutError:'
                    '' + str(retries) + ' retries to go.    ')
        except ClientResponseError as error:
            _LOGGER.error(
                    'ClientResponseError: '
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except Exception as error:
            template = "Unexpected exception of type {0} occurred. Arguments:{1!r}"
            message = template.format(type(error).__name__, error.args)
            _LOGGER.error(message)
        self.valid_token = False
        if retries == 0 or self.login_retries > 5:
            _LOGGER.error("To many retries. Abort now.")
            return False
        return await self.get_access_token(retries=retries - 1)

    async def _get_access_token(self):
        """Get access token with username and password registered in SMART app."""
        if self.username == '' or self.password == '':
            _LOGGER.error(
                "Please speficify username and password.")
            self.valid_token = False
            return False

        if(self.debug): print('get_access_token()')
        payload = {
            'AppToken': 'D8CBFF4C-2824-4342-B22D-189166FEF503',
            'MemId': self.username,
            'PW': self.password}
        headers = {
            'Pragma': 'no-cache',
            'Cache-Control': 'no-cache',
            'Expires': '-1',
            'Content-Type': 'application/json',
            'Charset': 'utf-8',
            'User-Agent': USERAGENT,
            'Host': self.host,
            'Connection': 'Keep-Alive'}

        async with self.session.post(
                'https://'+self.host+'/api/Userlogin1',
                data=json.dumps(payload),
                headers=headers) as response:

            if response.status != 200:
                self.login_retries += 1
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=response.status,
                    message=(
                        'Login to Panosonic SMART host error. '
                        'Please check if username and password is correct.'
                        'status = ' + str(response.status) + ', '
                        'data = ' + json.dumps(payload) + ', '
                        'headers = ' + json.dumps(headers) + '.'))
            else:
                if(self.debug):
                    print('Store token to file')
                response_json = await response.json()
                with open(self.cptoken_path, 'w') as outfile:
                    json.dump(response_json, outfile)
                outfile.close()
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
                self.valid_token = True
                return True

    async def check_access_token(self):
        """Check if the access token is expired and need to be refresh."""
        if(self.debug):
            print('check_access_token()')
        now = datetime.datetime.now()
        # CPToken expiring in 60 seconds or last call before 20mins
        if self.login_retries > 5:
            _LOGGER.error(
                "Too many login retries. Check username and password and network connection.")
            return False
        elif (not self.valid_token or
             (self.exp-now).total_seconds() < 60 or
             (self.lastcall - now).total_seconds() > 60*20):
                self.valid_token = False
                self.lastcall = now
                return await self.get_access_token()
        else:
            self.lastcall = now
            return True

    async def discover_devices(self, retries=3):
        """Discover devices registered in SMART app."""
        if(self.debug):
            print('discover_devices()')
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('No valid token.')
            return None
        try:
            with timeout(30):
                if self.session and not self.session.closed:
                    return await self._discover_devices()
                else:
                    if(self.debug):
                        print('create new clicentsession')
                    async with ClientSession() as self.session:
                        return await self._discover_devices()
        except asyncio.TimeoutError:
            _LOGGER.warning(
                'Timeout for appliances discovery. '
                '' + str(retries) + ' retries to go.    ')
        except ServerDisconnectedError as error:
            _LOGGER.warning(
                    'ServerDisconnectedError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except asyncio.TimeoutError as error:
            _LOGGER.error(
                    'asyncio.TimeoutError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except ClientResponseError as error:
            _LOGGER.error(
                    'ClientResponseError: '
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except UnicodeEncodeError:
            _LOGGER.warning("Setup your system local to support UTF8.")
            return self.appliances
        except Exception as error:
            template = "Unexpected exception of type {0} occurred. Arguments:{1!r}"
            message = template.format(type(error).__name__, error.args)
            _LOGGER.error(message)
            if self.appliances is not None:
                return self.appliances
        if retries == 0:
            # Finish all retries and got nothing.
            _LOGGER.error(
                'Discover devices failed after 3 retries.')
            return None
        # try to get new token
        if await self.get_access_token():
            return await self.discover_devices(retries=retries - 1)
        else:
            return None

    async def _discover_devices(self):
        """Discover devices registered in SMART app."""
        headers = {
           'Pragma': 'no-cache',
           'Cache-Control': 'no-cache',
           'Expires': '-1',
           'CPToken': self.CPToken,
           'Content-Type': 'application/json',
           'Charset': 'utf-8',
           'User-Agent': USERAGENT,
           'Host': self.host,
           'Connection': 'Keep-Alive'
        }

        async with self.session.get(
                    'https://'+self.host+'/api/UserGetRegisteredGWList1',
                    headers=headers) as response:

            if response.status != 200:
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=response.status,
                    message=(
                        "Discover devices failed. "
                        "status = " + str(response.status) + ', '
                        'headers = ' + json.dumps(headers) + "."))
            response_json = await response.json()
            _LOGGER.debug(
                '_discover_devices(): status:%d. response%s',
                response.status, json.dumps(response_json))
            gwlist = response_json.get('GWList')
            model_command_list = response_json.get('CommandList')
            _LOGGER.debug(
                '_discover_devices: gwlist:%s, command_list:%s',
                json.dumps(gwlist), json.dumps(model_command_list))
            if len(gwlist) == 0:
                _LOGGER.error(
                    "Please add gateways to your account first.")
                return None
            self.devices = []
            self.appliances = []
            for gw in gwlist:
                for dev in gw['Devices']:
                    dev['GWID'] = gw['GWID']
                    dev['auth'] = gw['auth']
                    self.devices.append(dev)
                    for model in model_command_list:
                        if model['ModelType'] == dev['ModelType']:
                            dev['CommandList'] = model['JSON'][0]
                            break
                    appliance = Appliance(dev, self, self.debug)
                    self.appliances.append(appliance)
                    if dev['AreaID'] not in self.area_list:
                        self.area_list.append(dev['AreaID'])

            if(self.debug):
                print('devices:', self.devices)
            return self.appliances

    async def device_status(self, device, commands, retries=3):
        """Get device status."""
        if(self.debug):
            print('device_status()')

        token_valid = await self.check_access_token()
        if not token_valid or commands is None or len(commands) == 0:
            _LOGGER.error(
                'No valid token or empty command list.')
            return None

        try:
            with timeout(30):
                if self.session and not self.session.closed:
                    return await self._device_status(device, commands)
                else:
                    async with ClientSession() as self.session:
                        return await self._device_status(device, commands)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                'Timeout for get status update from server. '
                '' + str(retries) + ' retries to go.    ')
        except ServerDisconnectedError as error:
            _LOGGER.warning(
                    'ServerDisconnectedError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except asyncio.TimeoutError as error:
            _LOGGER.error(
                    'asyncio.TimeoutError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except ClientResponseError as error:
            _LOGGER.error(
                    'ClientResponseError: '
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except Exception as error:
            template = "Unexpected exception of type {0} occurred. Arguments:{1!r}"
            message = template.format(type(error).__name__, error.args)
            _LOGGER.error(message)
            if retries == 0:
                return None
            return await self.device_status(
                            device, commands, retries=retries - 1)

    async def _device_status(self, device, commands):
        """Get device status."""
        headers = {
           'Pragma': 'no-cache',
           'Cache-Control': 'no-cache',
           'Expires': '-1',
           'CPToken': self.CPToken,
           'auth': device['auth'],
           'Content-Type': 'application/json',
           'Charset': 'utf-8',
           'User-Agent': USERAGENT,
           'Host': self.host,
           'Connection': 'Keep-Alive'
        }

        command_list = []
        for command in commands:
            command_list.append(
                {'CommandType': '{0:#0{1}x}'.format(command, 4)})

        payload = [{
            'CommandTypes': command_list,
            'DeviceID': int(device['DeviceID'])}]

        async with self.session.post(
                'https://'+self.host+'/api/DeviceGetInfo',
                data=json.dumps(payload),
                headers=headers) as response:

            if response.status != 200:
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=response.status,
                    message=(
                        'Get device status error. '
                        'status = ' + str(response.status) + ', '
                        'data = ' + json.dumps(payload) + ', '
                        'headers = ' + json.dumps(headers) + '.'))
            response_json = await response.json()
            info = response_json.get('devices')[0].get('Info')
            if response_json.get('status') == 'success':
                return info
            else:
                return None

    async def device_control(self, device, command_type, value, retries=3):
        """Send command to control the device."""
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('No valid token.')
            return False
        try:
            with timeout(30):
                if self.session and not self.session.closed:
                    return await self._device_control(device, command_type, value)
                else:
                    async with ClientSession() as self.session:
                        return await self._device_control(
                                        device, command_type, value)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                'Timeout for sending command to server. '
                '' + str(retries) + ' retries to go.    ')
        except ServerDisconnectedError as error:
            _LOGGER.warning(
                    'ServerDisconnectedError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except asyncio.TimeoutError as error:
            _LOGGER.error(
                    'asyncio.TimeoutError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except ClientResponseError as error:
            _LOGGER.error(
                    'ClientResponseError: '
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except Exception as error:
            template = "Unexpected exception of type {0} occurred. Arguments:{1!r}"
            message = template.format(type(error).__name__, error.args)
            _LOGGER.error(message)
            if retries == 0:
                return False
            return await self.device_control(
                            device, command_type, value, retries=retries - 1)

    async def _device_control(self, device, command_type, value):
        """Send command to control the device."""
        headers = {
           'Pragma': 'no-cache',
           'Cache-Control': 'no-cache',
           'Expires': '-1',
           'auth': device['auth'],
           'CPToken': self.CPToken,
           'Content-Type': 'application/json',
           'Charset': 'utf-8',
           'User-Agent': USERAGENT,
           'Host': self.host,
           'Connection': 'Keep-Alive'
        }
        command_url = ('https://' + self.host + ''
                       '/api/DeviceSetCommand?DeviceID='
                       '' + str(device['DeviceID']) + ''
                       '&commandType={0:#0{1}x}'.format(command_type+0x80, 4) + ''
                       '&Value=' + str(value))
        if(self.debug):
            print('command url to send:'+command_url)

        async with self.session.get(command_url, headers=headers) as response:
            if response.status != 200:
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=response.status,
                    message=(
                        'Device control error. '
                        'status = ' + str(response.status) + ', '
                        'headers = ' + json.dumps(headers) + '.'))
            response_json = await response.json()
            status = response_json.get('status') == 'success'
            return status

    async def get_power_log(self, device, retries=3):
        """Get power log from the device."""
        token_valid = await self.check_access_token()
        if not token_valid:
            _LOGGER.error('No valid token.')
            return False
        try:
            with timeout(30):
                if self.session and not self.session.closed:
                    return await self._get_power_log(device)
                else:
                    async with ClientSession() as self.session:
                        return await self._get_power_log(device)
        except asyncio.TimeoutError:
            _LOGGER.warning(
                'Timeout for sending command to server. '
                '' + str(retries) + ' retries to go.    ')
        except ServerDisconnectedError as error:
            _LOGGER.warning(
                    'ServerDisconnectedError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except asyncio.TimeoutError as error:
            _LOGGER.error(
                    'asyncio.TimeoutError:'
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except ClientResponseError as error:
            _LOGGER.error(
                    'ClientResponseError: '
                    '' + str(retries) + ' retries to go.    '
                    ' Error message: ' + error.message + '')
        except Exception as error:
            template = "Unexpected exception of type {0} occurred. Arguments:{1!r}"
            message = template.format(type(error).__name__, error.args)
            _LOGGER.error(message)
            if retries == 0:
                return False
            return await self.get_power_log(
                            device, retries=retries - 1)

    async def _get_power_log(self, device):
        """Get power log from the device."""
        headers = {
           'Pragma': 'no-cache',
           'Cache-Control': 'no-cache',
           'Expires': '-1',
           'auth': device['auth'],
           'Origin': 'file://',
           'CPToken': self.CPToken,
           'Content-Type': 'application/json',
           'Charset': 'utf-8',
           'User-Agent': USERAGENT,
           'Host': self.host,
           'Connection': 'Keep-Alive'
        }

        payload = {
            'gw_id': device['GWID'],
            'aread_ids': [0],
            'from': datetime.datetime.now().strftime('%Y/%m/%d'),
            'unit':'hour',
            'max_num':24
            }
        print(payload)
        print('url:'+'https://'+self.host+'/api/PowerGetCTAreaLog')
        async with self.session.post(
                'https://'+self.host+'/api/PowerGetCTAreaLog',
                data=json.dumps(payload),
                headers=headers) as response:

            if response.status != 200:
                raise ClientResponseError(
                    request_info=None,
                    history=None,
                    status=response.status,
                    message=(
                        'Get power log error. '
                        'status = ' + str(response.status) + ', '
                        'data = ' + json.dumps(payload) + ', '
                        'headers = ' + json.dumps(headers) + '.'))
            response_json = await response.json()
            print(response_json)
            info = response_json.get('Areas')[0].get('kwh')
            if response_json.get('status') == 'success':
                return info
            else:
                return None


    def get_all_appliances(self):
        """Get all discovered appliances object list."""
        return self.appliances

    def get_appliance_by_name(self, name):
        """Get the appliance object by name."""
        if self.appliances is None:
            return None
        for appliance in self.appliances:
            if appliance.get_name() == name:
                return appliance
        return None

    def get_appliance_by_id(self, id):
        """Get the appliance object by id."""
        if self.appliances is None:
            return None
        for appliance in self.appliances:
            if appliance.get_id() == id:
                return appliance
        return None

    # async update all appliance status.
    async def async_update(self):
        """Async update status of all appliances."""
        for appliance in self.appliances:
            await appliance.async_update()


class Appliance:
    """Appliance class."""

    def __init__(self, device, api, debug=False):
        """Intialize appliance object."""
        self.api = api
        self.device = device
        self.device_id = device['DeviceID']
        self.type = int(device['DeviceType'])
        self.name = device['NickName']
        self.area_id = device['AreaID']
        self.model_type = device['ModelType']
        self.model = device['Model']
        self.gwid = device['GWID']
        self.auth = device['auth']
        self.id = self.gwid+'.'+str(self.device_id)
        self.target_temperature = 0
        self.outside_temperature = 0
        self.inside_temperature = 0
        self.fan_mode = ''
        self.swing_mode = ''
        self.operation_mode = ''
        self.preset_mode = ''
        self.power = ''
        self.last_update = None
        self.debug = debug
        self.temp_min = 16
        self.temp_max = 30
        self.humidity_min = 40
        self.humidity_max = 70
        self.fan_min = 0
        self.fan_max = 0
        self.swing_min = 0
        self.swing_max = 0
        self.operation_mode_list=[]
        self.preset_mode_list=[]
        self.fan_mode_list=[]
        self.swing_mode_list=[]
        self.humidity_mode_list=[]
        self.tank_full = False
        self.humidity = 0
        self.target_humidity = 60
        self.ac_operation_mode_list = \
            ['cool', 'dry', 'fan', 'auto', 'heat']
        self.dehumi_preset_mode_list = \
             ['continuous', 'auto',  'clean', 'fan', 'clothes', 'cloeth dry', 'fixed humidity']

        self.setup_command_list(device)

    def setup_command_list(self, device):
        """Setup appliance parameters according to the command list in device object."""
        for command in device['CommandList']['list']:
            if command['CommandType'] == '0x01': #supported operation modes
                if self.type == 1: #AC
                    self.operation_mode_list.append('off')
                    for mode in command['Parameters']:
                        self.operation_mode_list.append(self.ac_operation_mode_list[mode[1]])

                elif self.type == 4: #Dehumidifier
                    self.operation_mode_list.append('off')
                    self.operation_mode_list.append('dry')
                    for mode in command['Parameters']:
                        self.preset_mode_list.append(self.dehumi_preset_mode_list[mode[1]])
                    if(self.debug):
		                      print('Supported dehumi preset modes:'+json.dumps(self.preset_mode_list))
                else:
                    _LOGGER.error('Unsupported device type: %d', self.type)
                if(self.debug):
                    print('Supported operation mode list:'+json.dumps(self.operation_mode_list))
            elif command['CommandType'] == '0x02' and self.type == 1: #AC supported fan modes
                for mode in command['Parameters']:
                    if mode[0] == 'Auto':
                        self.fan_mode_list.append('auto')
                    if mode[0] == 'Min':
                        self.fan_min = int(mode[1])
                    if mode[0] == 'Max':
                        self.fan_max = int(mode[1])
                    if self.fan_max > self.fan_min:
                        for level in range(self.fan_min, self.fan_max+1):
                            self.fan_mode_list.append(str(level))
                if(self.debug):
                    print('Supported fan mode list:'+json.dumps(self.fan_mode_list))
            elif command['CommandType'] == '0x03' and self.type == 1: #AC supported temperature range
                for mode in command['Parameters']:
                    if mode[0] == 'Min':
                        self.temp_min = int(mode[1])
                    if mode[0] == 'Max':
                        self.temp_max = int(mode[1])
                if(self.debug):
                    print('Supported min target temperature ='+ str(self.temp_min) + '; Supported max target temperature=' + str(self.temp_max))
            elif command['CommandType'] == '0x0f' and self.type == 1: #AC supported swing mode list
                for mode in command['Parameters']:
                    if mode[0] == 'Auto':
                        self.swing_mode_list.append('auto')
                    if mode[0] == 'Min':
                        self.swing_min = int(mode[1])
                    if mode[0] == 'Max':
                        self.swing_max = int(mode[1])
                    if self.swing_max > self.swing_min:
                        for level in range(self.swing_min, self.swing_max+1):
                            self.swing_mode_list.append(str(level))
                if(self.debug):
                    print('Supported swing mode list:'+json.dumps(self.swing_mode_list))
            elif command['CommandType'] == '0x0E' and self.type == 4: #Dehumidifer supported fan mode list
                for mode in command['Parameters']:
                    if mode[1] == 0:
                        self.fan_mode_list.append('auto')
                    if mode[1] == 1:
                        self.fan_mode_list.append('max')
                    if mode[1] == 2:
                        self.fan_mode_list.append('standard')
                    if mode[1] == 3:
                        self.fan_mode_list.append('quiet')
                if(self.debug):
                    print('Supported fan mode list:'+json.dumps(self.fan_mode_list))
            elif command['CommandType'] == '0x09' and self.type == 4: #Dehumidifer supported swing mode list
                for mode in command['Parameters']:
                    if mode[1] == 0:
                        self.swing_mode_list.append('stop')
                    if mode[1] == 1:
                        self.swing_mode_list.append('down')
                    if mode[1] == 2:
                        self.swing_mode_list.append('up')
                    if mode[1] == 3:
                        self.swing_mode_list.append('all')
                if(self.debug):
                    print('Supported fan mode list:'+json.dumps(self.fan_mode_list))
            elif command['CommandType'] == '0x04' and self.type == 4: #Dehumidifer supported himidity mode list
                for mode in command['Parameters']:
                    self.humidity_mode_list.append(mode[0])
                self.humidity_min = int(self.humidity_mode_list[0][0:2])
                self.humidity_max = int(self.humidity_mode_list[-1][0:2])
                if(self.debug):
                    print('Supported humidity mode list:'+json.dumps(self.humidity_mode_list))

    def get_fan_mode_list(self):
        """Return list of supported fan modes."""
        return self.fan_mode_list

    def get_fan_max_level(self):
        """Return the max fan mode."""
        return str(self.fan_max)

    def get_swing_mode_list(self):
        """Return list of supported swing modes."""
        return self.swing_mode_list

    def get_operation_mode_list(self):
        """Return list of supported operation modes."""
        return self.operation_mode_list

    def get_preset_mode_list(self):
        """Return list of supported operation modes."""
        #return ['off', 'cool', 'dry', 'auto', 'heat']
        if self.type == 4: #Dehumidifier
            return self.preset_mode_list
        else:
            return None

    def get_temp_min(self):
        """Return list of supported minimum target temperature."""
        return self.temp_min

    def get_temp_max(self):
        """Return list of supported maximum target temperature."""
        return self.temp_max

    def get_humidity_min(self):
        """Return list of supported minimum target humidity."""
        return self.humidity_min

    def get_humidity_max(self):
        """Return list of supported maximum target humidity."""
        return self.humidity_max

    def get_model(self):
        """Return the appliance model info."""
        return self.model

    def get_id(self):
        """Return the appliance uniques id (GWID + DevID)."""
        return self.id

    def get_gwid(self):
        """Return the appliance uniques id (GWID + DevID)."""
        return self.gwid

    def get_device_type(self):
        """Return the appliance device type."""
        return self.type

    def get_area_id(self):
        """Return the appliance area id."""
        return self.area_id

    def get_name(self):
        """Return the appliance nickname."""
        return self.name

    async def get_power_log(self):
        """Return hourly power of of the appliance."""
        return await self.api.get_power_log(self.device)


    async def async_update(self):
        """Async update appliance status.

        Return True if update succeess.

        """
        if self.power == 'off': #stop async_update if appliance is off
            return
        if self.last_update is not None:
            delta = datetime.datetime.now()-self.last_update
            if delta.total_seconds() < 300:
                if(self.debug):
                    print(('async_update() too frequent. Last: '
                           '' + self.last_update.strftime("%H:%M:%S") + ''
                           '; delta:' + str(delta) + ''))
                _LOGGER.debug(
                    "async_update() too frequennt. Last: %s; delta:%s",
                    self.last_update.strftime("%H:%M:%S"), str(delta))
                return
            else:
                if(self.debug):
                    print(('async_update() last: '
                           '' + self.last_update.strftime("%H:%M:%S") + ''
                           '; delta:' + str(delta) + ''))
                _LOGGER.debug(
                    "async_update() last:%s; delta=%s",
                    self.last_update.strftime("%H:%M:%S"), str(delta))

        self.last_update = datetime.datetime.now()
        if self.type == 1: #AC
            info = await self.api.device_status(self.device,
                                                [0, 1, 4, 0x21, 2, 0xf, 3])
            if info is None or len(info) != 7:
                _LOGGER.error("%s async_update() failed.", self.name)
            else:
                if info[0]['status'] is not None and info[0]['status'] == '0':
                    self.power = 'off'
                    self.operation_mode = 'off'
                else:
                    self.power = 'on'
                    self.operation_mode = self.ac_operation_mode_list[int(info[1]['status'])]
                self.target_temperature = int(info[6]['status'])
                self.inside_temperature = int(info[2]['status'])
                self.outside_temperature = int(info[3]['status'])
                if info[4]['status'] is not None and info[4]['status'] == '0':
                    self.fan_mode = 'auto'
                else:
                    self.fan_mode = info[4]['status']
                if info[5]['status'] is not None and info[5]['status'] == '0':
                    self.swing_mode = 'auto'
                else:
                    self.swing_mode = str(info[5]['status'])
        if self.type == 4: #Dehumidifier
            info = await self.api.device_status(self.device,
                                                [0x50, 0, 1, 7, 0xa, 4])
            if(self.debug):
                print('info:', info)
            if info is None or len(info) != 6:
                _LOGGER.error("%s async_update() failed.")
            else:
                if info[1]['status'] is not None and info[1]['status'] == '0':
                    self.power = 'off'
                    self.operation_mode = 'off'
                else:
                    self.power = 'on'
                    self.operation_mode = 'dry'
                    self.preset_mode = self.dehumi_preset_mode_list[int(info[2]['status'])]

                self.humidity = int(info[3]['status']) #humity
                self.tank_full = info[4]['status'] == '1'
                self.target_humidity = int(self.humidity_mode_list[int(info[5]['status'])][0:2]) #target humity
                await self.async_update_fan_swing_mode()


        if(self.debug):
            print(self.get_status())
        _LOGGER.debug(
            "%s:async_update():%s", self.name, json.dumps(self.get_status()))

    def get_status(self):
        """Return current status from local stored values."""
        status = {}
        if self.type == 1:
            status['target_temperature'] = self.target_temperature
            status['swing_mode'] = self.swing_mode
            status['power'] = self.power
            status['operation_mode'] = self.operation_mode
            status['inside_temperature'] = self.inside_temperature
            status['outside_temperature'] = self.outside_temperature
            status['fan_mode'] = self.fan_mode
        elif self.type == 4:
            status['power'] = self.power
            status['target_humidity'] = self.target_humidity
            status['operation_mode'] = self.operation_mode
            status['preset_mode'] = self.preset_mode
            status['humidity'] = self.humidity
            status['fan_mode'] = self.fan_mode
            status['tank_full'] = self.tank_full
        return status

    async def async_update_operation_mode(self):
        """Async update appliance operation mode."""
        info = await self.api.device_status(self.device, [0, 1])
        if info[0]['status'] is not None and info[0]['status'] == '1':
            self.power = 'on'
        else:
            self.power = 'off'
        if self.power == 'off':
            self.operation_mode = 'off'
        elif self.type == 1: #AC
            self.operation_mode = self.ac_operation_mode_list[int(info[1]['status'])]
        elif self.type == 4: #dehumifier
            if info[0]['status'] is not None and info[0]['status'] == '0':
                self.operation_mode = 'off'
            else:
                self.operation_mode = 'dry'
            self.preset_mode = self.dehumi_preset_mode_list[int(info[1]['status'])]

    def get_fan_mode(self):
        """Return cuurent fan mode."""
        return self.fan_mode

    def get_operation_mode(self):
        """Return current operation mode."""
        return self.operation_mode

    def get_preset_mode(self):
        """Return current preset mode."""
        return self.preset_mode

    def get_swing_mode(self):
        """Return current swing mode."""
        return self.swing_mode

    async def async_update_temperatures(self):
        """Async update temperatures."""
        _LOGGER.debug("async_update_temperatures")
        info = await self.api.device_status(self.device, [4, 0x21, 2, 0xf, 3])
        self.target_temperature = int(info[4]['status'])
        self.swing_mode = info[3]['status']
        self.inside_temperature = int(info[0]['status'])
        self.outside_temperature = int(info[1]['status'])
        self.fan_mode = info[2]['status']

    async def async_update_humidity(self):
        """Async update temperatures."""
        _LOGGER.debug("async_update_humidity")
        info = await self.api.device_status(self.device, [4, 7, 0xa])
        self.humidity = int(info[1]['status']) #humity
        self.target_humidity = int(self.humidity_mode_list[int(info[0]['status'])][0:2]) #target humity
        self.tank_full = info[2]['status'] == '1'

    async def get_temperatures(self):
        """Return current temperatures."""
        status = {}
        status['target_temperature'] = self.target_temperature
        status['swing_mode'] = self.swing_mode
        status['inside_temperature'] = self.inside_temperature
        status['outside_temperature'] = self.outside_temperature
        status['fan_mode'] = self.fan_mode
        return status

    def get_target_temperature(self):
        """Return target temperatures."""
        return self.target_temperature

    def get_outside_temperature(self):
        """Return outside temperatures."""
        return self.outside_temperature

    def get_inside_temperature(self):
        """Return inside temperatures."""
        return self.inside_temperature

    def get_target_humidity(self):
        """Return the humidity we try to reach."""
        return self.target_humidity

    def get_current_humidity(self):
        """Return the current humidity."""
        return self.humidity

    def get_power(self):
        """Return power state ('on'/'off')."""
        return self.power

    def is_on(self):
        """Return true if power is on."""
        return self.power == 'on'

    def get_tank_full(self):
        """Return true if tank is full."""
        return self.tank_full

    async def set_power(self, command):
        """Set power with command ('on'/'off'). Return current power state ('on'/'off')."""
        #Update current operation state first.
        await self.async_update_operation_mode()
        if (command == 'on' and not self.is_on()) or (command == 'off' and self.is_on()):
            value = 1 if command == 'on' else 0
            await self.api.device_control(self. device, 0, value)
            await self.async_update_operation_mode()
        return self.get_power()

    async def power_on(self):
        """Turn power on."""
        return await self.set_power('on')
    async def power_off(self):
        """Turn power off."""
        return await self.set_power('off')

    async def set_preset_mode(self, command):
        """Set preset mode."""
        _LOGGER.debug("panasonic_ac_saa4.set_preset_mode() mode=%s", command)
        # Update current preset and operation mode .
        await self.async_update_operation_mode()
        if not command == self.preset_mode:
            await self.api.device_control(self. device, 1,  self.dehumi_preset_mode_list.index(command))
            await self.async_update_operation_mode()
        return self.preset_mode

    async def set_operation_mode(self, command):
        """Set operation mode."""
        _LOGGER.debug("panasonic_ac_saa4.set_operation_mode() mode=%s", command)
        # Update current operation mode first.
        await self.async_update_operation_mode()
        if not command == self.operation_mode:
            if command == 'off':
                if self.is_on():
                    await self.api.device_control(self. device, 0, 0)
            else:
                if not self.is_on():
                    await self.api.device_control(self. device, 0, 1)
                if self.type == 1: #AC
                    await self.api.device_control(self. device, 1,
                        self.ac_operation_mode_list.index(command))
                elif self.type == 4: #dehumidifier
                    if not self.is_on():
                            await self.api.device_control(self. device, 0, 1)
                    await self.api.device_control(self. device, 1,  6) #dry to target humidity
                    #await self.api.device_control(self. device, 1,  self.dehumi_operation_mode_list.index(command))
            await self.async_update_operation_mode()
        return self.operation_mode

    async def set_cooling_operation_mode(self):
        """Set operation mdoe to cooling."""
        return await self.set_operation_mode('cool')

    async def set_dehumid_operation_mode(self):
        """Set operation mdoe to dehumid."""
        return await self.set_operation_mode('dry')

    async def set_auto_operation_mode(self,):
        """Set operation mdoe to auto."""
        return await self.set_operation_mode('auto')

    async def set_heating_operation_mode(self):
        """Set operation mdoe to heating."""
        return await self.set_operation_mode('heat')

    async def async_update_fan_swing_mode(self):
        """Async update temperatures."""
        command = [2, 0xf]
        if self.type == 4: #dehumidifer
            command = [0xe, 0x9]

        info = await self.api.device_status(self.device, command)

        if self.type == 1: #AC
            if info[0]['status'] is not None and info[0]['status'] == '0':
                self.fan_mode = 'auto'
            else:
                self.fan_mode = info[0]['status']
            if info[1]['status'] is not None and info[1]['status'] == '0':
                self.swing_mode = 'auto'
            else:
                self.swing_mode = str(info[1]['status'])
        elif self.type == 4: #defhumidifier
            self.fan_mode = self.fan_mode_list[int(info[0]['status'])]
            self.swing_mode = self.swing_mode_list[int(info[1]['status'])]

    async def set_fan_mode(self, mode):
        """Set fan mdoe."""
        await self.async_update_fan_swing_mode()
        if not mode == self.fan_mode:
            if self.type == 1: #AC
                if mode == 'auto':
                    level = 0
                else:
                    level = int(mode)
                await self.api.device_control(self.device, 2, level)
            elif self.type == 4: #dehumidifer
                await self.api.device_control(self.device, 0xe, self.fan_mode_list.index(mode))
            await self.async_update_fan_swing_mode()
        return self.fan_mode

    async def set_target_temperature(self,  temperature):
        """Set target temperature."""
        await self.async_update_temperatures()
        if not temperature == self.target_temperature:
            if temperature > self.temp_max:
                temp = self.temp_max
            elif temperature < self.temp_min:
                temp = self.temp_min
            else:
                temp = temperature
            await self.api.device_control(self.device, 3, temp)
            await self.async_update_temperatures()
        return self.target_temperature

    async def set_target_humidity(self,  humidity):
        """Set target humidity."""
        await self.async_update_humidity()
        if not humidity == self.target_humidity:
            if humidity > self.humidity_max:
                humi = self.humidity_max
            elif humidity < self.humidity_min:
                humi = self.humidity_min
            else:
                humi = int(humidity)
        else:
                humi = int(humidity)
        humi = 5 * round(humi/5) #round to multiples of 5
        humi_index = self.humidity_mode_list.index(str(humi)+'%')
        _LOGGER.debug("panasonic_ac_saa4.set_target_humidity() humidity=%s, index = %d", humi, humi_index)
        await self.api.device_control(self.device, 4, humi_index)
        await self.async_update_humidity()
        return self.target_humidity

    async def set_swing_mode(self, mode):
        """Set swing mode."""
        await self.async_update_fan_swing_mode()
        if not mode == self.swing_mode:
            if self.type == 1: #AC
                if mode == 'auto':
                    value = 0
                else:
                    value = int(mode)
                await self.api.device_control(self.device, 0xf, value)
            elif self.type == 4: #dehumidifier
                await self.api.device_control(self.device, 9, self.swing_mode_list.index(mode))
            await self.async_update_fan_swing_mode()
        return self.swing_mode
