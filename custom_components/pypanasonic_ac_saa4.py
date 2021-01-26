"""Python example to control Panasonic smart appliances using SAAnet 4 standard."""

# import argparse
import asyncio


from panasonic_ac_saa4_api import PanasonicSAA4Api

async def main():
    """Main routing testing PanasonicSAA4Api."""
    pana_api = PanasonicSAA4Api(True)
    await pana_api.init('xxx', 'xxx')
    appliance = pana_api.get_appliance_by_name('BedRoom')
    #await appliance.set_swing_mode('1')
    #await appliance.set_target_temperature(26)
    #await appliance.set_operation_mode('fan')
    await appliance.async_update()
    print('Power:'+appliance.get_power())
    print('Operation Mode:'+appliance.get_operation_mode())
    print('Swing Mode:'+appliance.get_swing_mode())
    print('Fan Mode:'+appliance.get_fan_mode())
    print('Target Temperature:', appliance.get_target_temperature())
    print('Outside Temperature:', appliance.get_outside_temperature())
    print('Inside Temperature:', appliance.get_inside_temperature())
#    info = await appliance.get_power_log()
#    print('Power:', info)

loop = asyncio.get_event_loop()
loop.run_until_complete(main())
loop.close()
