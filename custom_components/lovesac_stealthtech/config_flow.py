"""Config flow: BLE auto-discovery on the service UUID + manual address."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_IDLE_TIMEOUT,
    CONF_MY_ARM_STYLE,
    CONF_MY_COUCH_SHAPE,
    CONF_MY_FABRIC,
    CONF_POLL_INTERVAL,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_POLL_INTERVAL,
    DOMAIN,
)


class StealthTechConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle discovery + manual setup."""

    VERSION = 1

    def __init__(self) -> None:
        self._discovery: BluetoothServiceInfoBleak | None = None

    # AUDIT (v0.3 D6b): discovery matches on the excelpoint.com service UUID
    # via manifest.json's bluetooth matcher — UUID matching is present and
    # authoritative, so no name matching is used. Fallback knowledge only:
    # the official app also recognizes hubs by BLE name prefixes "HK_Lovesac"
    # and "EE4034" (libstealthtech). If a hub firmware ever stops advertising
    # the service UUID, add a local_name matcher on those prefixes.
    async def async_step_bluetooth(
        self, discovery_info: BluetoothServiceInfoBleak
    ) -> ConfigFlowResult:
        await self.async_set_unique_id(discovery_info.address)
        self._abort_if_unique_id_configured()
        self._discovery = discovery_info
        self.context["title_placeholders"] = {
            "name": discovery_info.name or discovery_info.address
        }
        return await self.async_step_bluetooth_confirm()

    async def async_step_bluetooth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        assert self._discovery is not None
        if user_input is not None:
            return self.async_create_entry(
                title=self._discovery.name or "Lovesac StealthTech",
                data={"address": self._discovery.address},
            )
        return self.async_show_form(
            step_id="bluetooth_confirm",
            description_placeholders={
                "name": self._discovery.name or self._discovery.address
            },
        )

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            address = user_input["address"].strip().upper()
            await self.async_set_unique_id(address)
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title="Lovesac StealthTech", data={"address": address}
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Required("address"): str}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "StealthTechOptionsFlow":
        return StealthTechOptionsFlow()


class StealthTechOptionsFlow(OptionsFlow):
    """Options: poll interval + idle disconnect timeout."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(data=user_input)
        options = self.config_entry.options
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_POLL_INTERVAL,
                        default=options.get(CONF_POLL_INTERVAL, DEFAULT_POLL_INTERVAL),
                    ): vol.All(int, vol.Range(min=15, max=3600)),
                    vol.Optional(
                        CONF_IDLE_TIMEOUT,
                        default=options.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
                    ): vol.All(vol.Coerce(float), vol.Range(min=1.0, max=60.0)),
                    # v0.3 D4: local override labels for the raw enum sensors.
                    # Empty string = unset. Shipped-table bindings (e.g.
                    # LAYOUT_NAMES) always take precedence over these.
                    vol.Optional(
                        CONF_MY_COUCH_SHAPE,
                        default=options.get(CONF_MY_COUCH_SHAPE, ""),
                    ): str,
                    vol.Optional(
                        CONF_MY_ARM_STYLE,
                        default=options.get(CONF_MY_ARM_STYLE, ""),
                    ): str,
                    vol.Optional(
                        CONF_MY_FABRIC,
                        default=options.get(CONF_MY_FABRIC, ""),
                    ): str,
                }
            ),
        )
