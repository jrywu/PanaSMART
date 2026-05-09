
import json
import logging
import datetime

_LOGGER = logging.getLogger(__name__)

ASYNC_UPDATE_INTERVAL = 300

DEHUMI_PRESET_MODE_BY_VALUE = {
    "default": {
        0: "continuous",
        1: "auto",
        2: "clean",
        3: "fan",
        4: "clothes",
        5: "cloeth dry",
        6: "fixed humidity",
    },
    "NNW-L": {
        0: "continuous",
        1: "mold standby",
        3: "fan",
        4: "clothes",
        6: "fixed humidity",
        9: "smart energy",
        10: "quick dry",
        11: "silent dry",
    },
}

class PanasonicAppliance:
    """Panasonic IoT appliance class."""

    def __init__(self, device, core, debug=False):
        """Intialize appliance object."""
        self.core = core
        self.device = device
        self.device_id = device['DeviceID']
        self.type = int(device['DeviceType'])
        self.name = device['NickName']
        self.area_id = device['AreaID']
        self.model_type = device['ModelType']
        self.model = device['Model']
        self.gwid = device['GWID']
        self.auth = device['auth']
        self.id = self.gwid #+'.'+str(self.device_id)
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
        self.preset_mode_by_value={}
        self.preset_value_by_mode={}
        self.fan_mode_list=[]
        self.fan_mode_by_value={}
        self.fan_value_by_mode={}
        self.swing_mode_list=[]
        self.swing_mode_by_value={}
        self.swing_value_by_mode={}
        self.humidity_mode_list=[]
        self.tank_full = False
        self.humidity = 0
        self.target_humidity = 60
        self.ac_operation_mode_list = \
            ['cool', 'dry', 'fan', 'auto', 'heat']

        self.setup_command_list(device)

    def _get_dehumi_preset_mode_name(self, value, fallback):
        mode_map = DEHUMI_PRESET_MODE_BY_VALUE.get(self.model_type, DEHUMI_PRESET_MODE_BY_VALUE["default"])
        return mode_map.get(value, fallback)

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
                        value = int(mode[1])
                        preset_mode = self._get_dehumi_preset_mode_name(value, mode[0])
                        self.preset_mode_by_value[value] = preset_mode
                        self.preset_value_by_mode[preset_mode] = value
                        self.preset_mode_list.append(preset_mode)
                    if(self.debug):
                        _LOGGER.debug('Supported dehumi preset modes:'+json.dumps(self.preset_mode_list))
                else:
                    _LOGGER.error('Unsupported device type: %d', self.type)
                if(self.debug):
                    _LOGGER.debug('Supported operation mode list:'+json.dumps(self.operation_mode_list))
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
                    _LOGGER.debug('Supported fan mode list:'+json.dumps(self.fan_mode_list))
            elif command['CommandType'] == '0x03' and self.type == 1: #AC supported temperature range
                for mode in command['Parameters']:
                    if mode[0] == 'Min':
                        self.temp_min = int(mode[1])
                    if mode[0] == 'Max':
                        self.temp_max = int(mode[1])
                if(self.debug):
                    _LOGGER.debug('Supported min target temperature ='+ str(self.temp_min) + '; Supported max target temperature=' + str(self.temp_max))
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
                    _LOGGER.debug('Supported swing mode list:'+json.dumps(self.swing_mode_list))
            elif command['CommandType'] == '0x0E' and self.type == 4: #Dehumidifer supported fan mode list
                for mode in command['Parameters']:
                    value = int(mode[1])
                    self.fan_mode_by_value[value] = mode[0]
                    self.fan_value_by_mode[mode[0]] = value
                    self.fan_mode_list.append(mode[0])
                    # if mode[1] == 0:
                    #     self.fan_mode_list.append('auto')
                    # if mode[1] == 1:
                    #     self.fan_mode_list.append('max')
                    # if mode[1] == 2:
                    #     self.fan_mode_list.append('standard')
                    # if mode[1] == 3:
                    #     self.fan_mode_list.append('quiet')
                if(self.debug):
                    _LOGGER.debug('Supported fan mode list:'+json.dumps(self.fan_mode_list))
            elif command['CommandType'] == '0x09' and self.type == 4: #Dehumidifer supported swing mode list
                for mode in command['Parameters']:
                    value = int(mode[1])
                    self.swing_mode_by_value[value] = mode[0]
                    self.swing_value_by_mode[mode[0]] = value
                    self.swing_mode_list.append(mode[0])
                    # if mode[1] == 0:
                    #     self.swing_mode_list.append('stop')
                    # if mode[1] == 1:
                    #     self.swing_mode_list.append('down')
                    # if mode[1] == 2:
                    #     self.swing_mode_list.append('up')
                    # if mode[1] == 3:
                    #     self.swing_mode_list.append('all')
                if(self.debug):
                    _LOGGER.debug('Supported swing mode list:'+json.dumps(self.swing_mode_list))
            elif command['CommandType'] == '0x04' and self.type == 4: #Dehumidifer supported himidity mode list
                for mode in command['Parameters']:
                    self.humidity_mode_list.append(mode[0])
                self.humidity_min = int(self.humidity_mode_list[0][0:2])
                self.humidity_max = int(self.humidity_mode_list[-1][0:2])
                if(self.debug):
                    _LOGGER.debug('Supported humidity mode list:'+json.dumps(self.humidity_mode_list))

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

    async def get_power_log(self, year_back=0, months=12):
        """Return hourly power of of the appliance."""
        return await self.core.get_power_log(self.device, year_back, months)

    async def async_update(self, force=False):
        """Async update appliance status.
        Return True if update success.
        """
        if(self.debug):
            _LOGGER.debug(f"async_update()")

        if not force and self.last_update is not None:
            delta = datetime.datetime.now()-self.last_update
            if delta.total_seconds() < ASYNC_UPDATE_INTERVAL:
                if(self.debug):
                    _LOGGER.debug(
                        "async_update() too frequent. Last call: %s, %s seconds ago.",
                        self.last_update.strftime("%H:%M:%S"), delta.seconds)
                return

        self.last_update = datetime.datetime.now()
        if self.type == 1:# and self.power != 'off': #AC
            info = await self.core.device_status(self.device,[0,1,4])
            #                                    [0, 1, 4, 0x21, 2, 0xf, 3])
            if info is None or len(info) != 3:
                _LOGGER.error("%s async_update() failed.", self.name)
                return
            else:
                if info[0]['status'] is not None and info[0]['status'] == '0':
                    self.power = 'off'
                    self.operation_mode = 'off'
                else:
                    self.power = 'on'
                    self.operation_mode = self.ac_operation_mode_list[int(info[1]['status'])]
                self.inside_temperature = int(info[2]['status'])
                _LOGGER.debug(
                    "%s:async_update():%s", self.name, json.dumps(self.get_status()))
            info = await self.core.device_status(self.device,[0x21,3,2,0xf])
            if info is None or len(info) != 4:
                _LOGGER.error("%s async_update() failed.", self.name)
                return
            else:
                self.target_temperature = int(info[1]['status'])
                self.outside_temperature = int(info[0]['status'])
                if info[2]['status'] is not None and info[2]['status'] == '0':
                    self.fan_mode = 'auto'
                else:
                    self.fan_mode = str(info[2]['status'])
                if info[3]['status'] is not None and info[3]['status'] == '0':
                    self.swing_mode = 'auto'
                else:
                    self.swing_mode = str(info[3]['status'])
                #if(self.debug): _LOGGER.debug(self.get_status())
                _LOGGER.debug(
                    "%s:async_update():%s", self.name, json.dumps(self.get_status()))

        if self.type == 4:# and self.power != 'off': #Dehumidifier
            info = await self.core.device_status(self.device,
                                                [0x50, 0, 1, 7, 0xa, 4])
            if info is None or len(info) != 6:
                _LOGGER.error("%s async_update() failed.", self.name)
                return
            else:
                if(self.debug):
                    _LOGGER.debug(f'info:{info}')
                if info[1]['status'] is not None and info[1]['status'] == '0':
                    self.power = 'off'
                    self.operation_mode = 'off'
                else:
                    self.power = 'on'
                    self.operation_mode = 'dry'
                    self.preset_mode = self.preset_mode_by_value.get(
                        int(info[2]['status']), info[2]['status'])

                self.humidity = int(info[3]['status']) #humity
                self.tank_full = info[4]['status'] == '1'
                self.target_humidity = int(self.humidity_mode_list[int(info[5]['status'])][0:2]) #target humity
                await self.async_update_fan_swing_mode()

                if(self.debug):
                    _LOGGER.debug(self.get_status())
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
        if(self.debug): _LOGGER.debug('async_update_operation_mode()')
        info = await self.core.device_status(self.device, [0, 1])
        if info is None:
            _LOGGER.error(
                "%s:async_update_operation_mode() update status failed", self.name)
            return
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
            self.preset_mode = self.preset_mode_by_value.get(
                int(info[1]['status']), info[1]['status'])

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
        info = await self.core.device_status(self.device, [4, 0x21, 2, 0xf, 3])
        if info is None:
            _LOGGER.error(
                "%s:async_update_temperatures() update status failed", self.name)
            return
        self.target_temperature = int(info[4]['status'])
        self.swing_mode = info[3]['status']
        self.inside_temperature = int(info[0]['status'])
        self.outside_temperature = int(info[1]['status'])
        self.fan_mode = info[2]['status']

    async def async_update_humidity(self):
        """Async update temperatures."""
        _LOGGER.debug("async_update_humidity")
        info = await self.core.device_status(self.device, [4, 7, 0xa])
        if info is None:
            _LOGGER.error(
                "%s:async_update_humidity() update status failed", self.name)
            return
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
            await self.core.device_control(self.device, 0, value)
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
            value = self.preset_value_by_mode.get(command)
            if value is None:
                _LOGGER.error("%s set_preset_mode() unsupported mode: %s", self.name, command)
                return self.preset_mode
            await self.core.device_control(self.device, 1, value)
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
                    await self.core.device_control(self.device, 0, 0)
            else:
                if not self.is_on():
                    await self.core.device_control(self.device, 0, 1)
                if self.type == 1: #AC
                    await self.core.device_control(self.device, 1,
                        self.ac_operation_mode_list.index(command))
                elif self.type == 4: #dehumidifier
                    if not self.is_on():
                            await self.core.device_control(self.device, 0, 1)
                    value = self.preset_value_by_mode.get('fixed humidity', 6)
                    await self.core.device_control(self.device, 1, value) #dry to target humidity
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

        info = await self.core.device_status(self.device, command)
        if info is None:
            _LOGGER.error(
                "%s:async_update_fan_swing_mode() update status failed", self.name)
            return

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
            self.fan_mode = self.fan_mode_by_value.get(
                int(info[0]['status']), info[0]['status'])
            self.swing_mode = self.swing_mode_by_value.get(
                int(info[1]['status']), info[1]['status'])

    async def set_fan_mode(self, mode):
        """Set fan mdoe."""
        await self.async_update_fan_swing_mode()
        if not mode == self.fan_mode:
            if self.type == 1: #AC
                if mode.lower() == 'auto' or mode == '自動':
                    level = 0
                else:
                    level = int(mode)
                await self.core.device_control(self.device, 2, level)
            elif self.type == 4: #dehumidifer
                value = self.fan_value_by_mode.get(mode)
                if value is None:
                    _LOGGER.error("%s set_fan_mode() unsupported mode: %s", self.name, mode)
                    return self.fan_mode
                await self.core.device_control(self.device, 0xe, value)
            await self.async_update_fan_swing_mode()
        return self.fan_mode

    async def set_target_temperature(self, temperature):
        """Set target temperature."""
        await self.async_update_temperatures()
        if not temperature == self.target_temperature:
            if temperature > self.temp_max:
                temp = self.temp_max
            elif temperature < self.temp_min:
                temp = self.temp_min
            else:
                temp = temperature
            await self.core.device_control(self.device, 3, temp)
            await self.async_update_temperatures()
        return self.target_temperature

    async def set_target_humidity(self, humidity):
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
        await self.core.device_control(self.device, 4, humi_index)
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
                await self.core.device_control(self.device, 0xf, value)
            elif self.type == 4: #dehumidifier
                value = self.swing_value_by_mode.get(mode)
                if value is None:
                    _LOGGER.error("%s set_swing_mode() unsupported mode: %s", self.name, mode)
                    return self.swing_mode
                await self.core.device_control(self.device, 9, value)
            await self.async_update_fan_swing_mode()
        return self.swing_mode
    
    async def get_power_log(self, year_back=0, months=12):
        """Return power log for the appliance."""
        response_json = await self.core.get_power_log(year_back, months)
        if response_json is not None and isinstance(response_json, dict):
            for result in response_json.get('GwList', []):
                if result.get('GwID') == self.gwid:
                    return result
        return None
