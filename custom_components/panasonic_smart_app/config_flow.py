"""Config flow for the Daikin platform."""
import asyncio
import logging

from aiohttp import ClientError
from async_timeout import timeout

from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD, CONF_HOST
import homeassistant.helpers.config_validation as cv
import voluptuous as vol

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


@config_entries.HANDLERS.register(DOMAIN)
class panaSMARTCongfiFlowHandler(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_CLOUD_POLL

    async def async_step_user(self, user_input=None):
        """User initiated config flow."""
        if user_input is None:
            return self.async_show_form(
                step_id=config_entries.SOURCE_USER,
                data_schema=vol.Schema({
                    vol.Required(CONF_USERNAME): str,
                    vol.Required(CONF_PASSWORD): str,
                    vol.Optional(CONF_HOST,
                                 default='ems2.panasonic.com.tw'): str,
                })
            )
        #return await self.async_abort(reason='already_configure')
        return await self.async_step_import(user_input)

    async def async_step_import(self, config):
        """Import a config entry."""
        _LOGGER.debug("panasonic_ac_saa4.async_step_import():")
        for entry in self._async_current_entries():
            if entry.title == 'PanaSMART':
                _LOGGER.debug("panasonic_ac_saa4.async_step_import(): \
                              config entry exist!!")
                return self.async_abort(reason='already_configured')
        _LOGGER.debug("panasonic_ac_saa4.async_step_import(): creating \
                      new config entry")
        return self.async_create_entry(title='PanaSMART', data=config)

    async def async_step_discovery(self, user_input):
        """Initialize step from discovery."""
        pass
