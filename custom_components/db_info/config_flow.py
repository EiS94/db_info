import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntityFilterSelectorConfig,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
)

from .bahn_api import get_trip_info
from .const import (
    ALL_TRANSPORT_TYPES,
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
    CONF_MAX_TRANSFERS,
    CONF_START,
    CONF_TRANSPORT_TYPES,
    CONF_UPDATE_INTERVAL,
    CONNECTION_ALL,
    CONNECTION_CUSTOM,
    CONNECTION_LONG_DISTANCE,
    CONNECTION_REGIONAL,
    DOMAIN,
    TRANSPORT_TYPES_ALL,
)

_LOGGER = logging.getLogger(__name__)

# Human-readable labels for individual transport types
TRANSPORT_TYPE_LABELS = {
    "SBAHN": "S-Bahn",
    "UBAHN": "U-Bahn",
    "TRAM": "Tram",
    "BUS": "Bus",
    "SCHIFF": "Schiff",
    "AST/RUFBUS": "AST/Rufbus",
    "ICE": "ICE",
    "IC/EC": "IC/EC",
    "NAHVERKEHR": "Nahverkehr",
    "SONSTIGE": "Sonstige"
}

CONNECTION_TYPE_OPTIONS = [
    {"value": CONNECTION_ALL, "label": "Alle Verkehrsmittel"},
    {"value": CONNECTION_REGIONAL, "label": "Nur Nahverkehr"},
    {"value": CONNECTION_LONG_DISTANCE, "label": "Nur Fernverkehr"},
    {"value": CONNECTION_CUSTOM, "label": "Benutzerdefiniert \u2026"},
]

TRANSPORT_TYPE_OPTIONS = [
    {"value": k, "label": v} for k, v in TRANSPORT_TYPE_LABELS.items()
]


def _build_main_schema(valid_inputs):
    return vol.Schema(
        {
            vol.Required(CONF_START): EntitySelector(
                EntityFilterSelectorConfig(include_entities=valid_inputs)
            ),
            vol.Required(CONF_DESTINATION): EntitySelector(
                EntityFilterSelectorConfig(include_entities=valid_inputs)
            ),
            vol.Required(
                CONF_CONNECTION_TYPE, default=CONNECTION_ALL
            ): SelectSelector(
                SelectSelectorConfig(
                    options=CONNECTION_TYPE_OPTIONS,
                    mode="dropdown",
                )
            ),
            vol.Optional(CONF_UPDATE_INTERVAL, default=10): NumberSelector(
                NumberSelectorConfig(min=1, max=60, mode=NumberSelectorMode.BOX)
            ),
            vol.Optional(CONF_MAX_TRANSFERS): NumberSelector(
                NumberSelectorConfig(min=0, max=9, mode=NumberSelectorMode.BOX)
            ),
        }
    )


def _build_custom_schema(current_types=None):
    return vol.Schema(
        {
            vol.Required(
                CONF_TRANSPORT_TYPES,
                default=current_types or TRANSPORT_TYPES_ALL,
            ): SelectSelector(
                SelectSelectorConfig(
                    options=TRANSPORT_TYPE_OPTIONS,
                    multiple=True,
                    mode=SelectSelectorMode.LIST,
                )
            ),
        }
    )


def _build_options_schema(current_connection_type, current_interval, current_max_transfers=None):
    schema = {
        vol.Required(
            CONF_CONNECTION_TYPE, default=current_connection_type
        ): SelectSelector(
            SelectSelectorConfig(
                options=CONNECTION_TYPE_OPTIONS,
                mode="dropdown",
            )
        ),
        vol.Required(
            CONF_UPDATE_INTERVAL, default=current_interval
        ): NumberSelector(
            NumberSelectorConfig(min=1, max=60, mode=NumberSelectorMode.BOX)
        ),
    }
    # Optional field: leave empty to allow any number of transfers (default).
    if current_max_transfers is None:
        schema[vol.Optional(CONF_MAX_TRANSFERS)] = NumberSelector(
            NumberSelectorConfig(min=0, max=9, mode=NumberSelectorMode.BOX)
        )
    else:
        schema[vol.Optional(CONF_MAX_TRANSFERS, default=current_max_transfers)] = NumberSelector(
            NumberSelectorConfig(min=0, max=9, mode=NumberSelectorMode.BOX)
        )
    return vol.Schema(schema)


class DBInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data = {}

    async def _test_connection(
        self, start_entity_id, destination_entity_id, connection_type,
        transport_types=None, max_transfers=None,
    ):
        """Try a real trip request to make sure at least one backend is reachable.

        Returns True if at least one source returned usable journeys,
        False otherwise (including if the entities have no coordinates
        yet, e.g. a person who hasn't reported a location).
        """
        start_state = self.hass.states.get(start_entity_id)
        dest_state = self.hass.states.get(destination_entity_id)
        if start_state is None or dest_state is None:
            return False

        start_attrs = start_state.attributes
        dest_attrs = dest_state.attributes
        if "latitude" not in start_attrs or "longitude" not in start_attrs:
            return False
        if "latitude" not in dest_attrs or "longitude" not in dest_attrs:
            return False

        start_coords = (start_attrs["latitude"], start_attrs["longitude"])
        dest_coords = (dest_attrs["latitude"], dest_attrs["longitude"])

        try:
            result = await get_trip_info(
                start_coords,
                dest_coords,
                connection_type=connection_type,
                transport_types=transport_types,
                max_transfers=max_transfers,
            )
        except Exception:  # pylint: disable=broad-except
            _LOGGER.exception("Error testing connection during config flow")
            return False

        return bool(result.get("journeys"))

    async def async_step_user(self, user_input=None):
        errors = {}

        all_persons = self.hass.states.async_all("person")
        valid_persons = [
            p.entity_id
            for p in all_persons
            if "latitude" in p.attributes and "longitude" in p.attributes
        ]
        valid_inputs = valid_persons + [
            z.entity_id for z in self.hass.states.async_all("zone")
        ]

        if not valid_inputs:
            errors["base"] = "no_entities_with_coordinates"

        if user_input is not None and not errors:
            await self.async_set_unique_id(
                f"{user_input[CONF_START]}::{user_input[CONF_DESTINATION]}"
            )
            self._abort_if_unique_id_configured()

            self._data = user_input

            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_CUSTOM:
                return await self.async_step_custom_types()

            connected = await self._test_connection(
                user_input[CONF_START],
                user_input[CONF_DESTINATION],
                user_input[CONF_CONNECTION_TYPE],
                max_transfers=user_input.get(CONF_MAX_TRANSFERS),
            )
            if not connected:
                errors["base"] = "cannot_connect"
            else:
                start_state = self.hass.states.get(user_input[CONF_START])
                dest_state = self.hass.states.get(user_input[CONF_DESTINATION])
                start_name = start_state.name if start_state else user_input[CONF_START]
                dest_name = dest_state.name if dest_state else user_input[CONF_DESTINATION]

                return self.async_create_entry(
                    title=f"{start_name} -> {dest_name}",
                    data={
                        CONF_START: user_input[CONF_START],
                        CONF_DESTINATION: user_input[CONF_DESTINATION],
                        CONF_CONNECTION_TYPE: user_input[CONF_CONNECTION_TYPE],
                    },
                    options={
                        CONF_UPDATE_INTERVAL: user_input.get(CONF_UPDATE_INTERVAL, 10),
                        CONF_MAX_TRANSFERS: user_input.get(CONF_MAX_TRANSFERS),
                    },
                )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_main_schema(valid_inputs),
            errors=errors,
        )

    async def async_step_custom_types(self, user_input=None):
        errors = {}

        if user_input is not None:
            connected = await self._test_connection(
                self._data[CONF_START],
                self._data[CONF_DESTINATION],
                CONNECTION_CUSTOM,
                transport_types=user_input[CONF_TRANSPORT_TYPES],
                max_transfers=self._data.get(CONF_MAX_TRANSFERS),
            )
            if not connected:
                errors["base"] = "cannot_connect"
            else:
                start_state = self.hass.states.get(self._data[CONF_START])
                dest_state = self.hass.states.get(self._data[CONF_DESTINATION])
                start_name = start_state.name if start_state else self._data[CONF_START]
                dest_name = dest_state.name if dest_state else self._data[CONF_DESTINATION]

                return self.async_create_entry(
                    title=f"{start_name} -> {dest_name}",
                    data={
                        CONF_START: self._data[CONF_START],
                        CONF_DESTINATION: self._data[CONF_DESTINATION],
                        CONF_CONNECTION_TYPE: CONNECTION_CUSTOM,
                        CONF_TRANSPORT_TYPES: user_input[CONF_TRANSPORT_TYPES],
                    },
                    options={
                        CONF_UPDATE_INTERVAL: self._data.get(CONF_UPDATE_INTERVAL, 10),
                        CONF_MAX_TRANSFERS: self._data.get(CONF_MAX_TRANSFERS),
                    },
                )

        return self.async_show_form(
            step_id="custom_types",
            data_schema=_build_custom_schema(),
            errors=errors,
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return DBInfoOptionsFlowHandler()


class DBInfoOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self):
        self._options = {}

    async def async_step_init(self, user_input=None):
        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, 10),
        )
        current_connection_type = self.config_entry.options.get(
            CONF_CONNECTION_TYPE,
            self.config_entry.data.get(CONF_CONNECTION_TYPE, CONNECTION_ALL),
        )
        current_max_transfers = self.config_entry.options.get(
            CONF_MAX_TRANSFERS,
            self.config_entry.data.get(CONF_MAX_TRANSFERS, None),
        )

        if user_input is not None:
            self._options = user_input

            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_CUSTOM:
                return await self.async_step_custom_types()

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(
                current_connection_type, current_interval, current_max_transfers
            ),
        )

    async def async_step_custom_types(self, user_input=None):
        current_types = self.config_entry.options.get(
            CONF_TRANSPORT_TYPES,
            self.config_entry.data.get(CONF_TRANSPORT_TYPES, TRANSPORT_TYPES_ALL),
        )

        if user_input is not None:
            return self.async_create_entry(
                title="",
                data={
                    **self._options,
                    CONF_TRANSPORT_TYPES: user_input[CONF_TRANSPORT_TYPES],
                },
            )

        return self.async_show_form(
            step_id="custom_types",
            data_schema=_build_custom_schema(current_types),
        )
