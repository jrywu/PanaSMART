"""Python example to control Panasonic smart appliances using SAAnet 4 standard."""

# import argparse
import asyncio
import datetime
from aiohttp import ClientSession

from panasonic_iot_tw_api import panasonic_iot_tw_api
from panasonic_iot_tw_api import Appliance
import logging

# Configure logging
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Create a logger instance
_LOGGER = logging.getLogger(__name__)

async def my_async_function():
    # Your async code here
    pana_api = panasonic_iot_tw_api(True)
    session = ClientSession()
    appliances = await pana_api.init('xxx', 'xxxxx',session)
    await pana_api.async_update()
    if appliances is None:
        print('Got nothing from Panasonic SAA4 interface.')
    appliance = pana_api.get_appliance_by_name('DehumiBedroom')
    #await appliance.set_swing_mode('1')
    #await appliance.set_target_temperature(26)
    #await appliance.set_operation_mode('fan')
    #await appliance.power_on()
    await appliance.async_update_operation_mode()
    await appliance.async_update()
    #    print('Power:'+appliance.get_power())
    print(f'Operation Mode:{appliance.get_operation_mode()}')
    print(f'Swing Mode: {appliance.get_swing_mode()}')
    print(f'Fan Mode:{appliance.get_fan_mode_list()}')
    #print('Target Temperature:', appliance.get_target_temperature())
    #print('Outside Temperature:', appliance.get_outside_temperature())
    #print('Inside Temperature:', appliance.get_inside_temperature())
    info = await appliance.get_power_log(
        unit='hour',
        from_date=datetime.date.today(),
        max_num=24,
    )
    print('Power:', info)
    await session.close()

async def main():
    try:
        await asyncio.wait_for(my_async_function(), timeout=90)  # This will
        """Main routing testing PanasonicSAA4Api."""

    except asyncio.TimeoutError:
        print("Operation timed out!")

# Run the main function
if __name__ == "__main__":
    asyncio.run(main())
# loop = asyncio.get_event_loop()
# loop.run_until_complete(main())
# loop.close()
