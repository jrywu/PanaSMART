"""Python module to control Panasonic SMART appliances supporting SAAnet 4 protocol."""
import logging
from .core import core
from .PanasonicAppliance import PanasonicAppliance as Appliance

_LOGGER = logging.getLogger(__name__)

PANASMARTHOST = 'ems2.panasonic.com.tw'

class panasonic_iot_tw_api:
    """Panasonic SMART appliances control interface with SAAnet 4 protocol."""

    def __init__(self, debug=False):
        """Initialize the interface."""
        self.appliances = None
        self.core=core(debug)
        
        
    async def init(self, username, password, session=None, host=PANASMARTHOST):
        self.appliances = await self.core.init(username, password, session, host)
        return self.appliances

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
    async def async_update(self, force=False):
        """Async update status of all appliances."""
        if self.appliances is not None:
            for appliance in self.appliances:
                await appliance.async_update(force=force)

