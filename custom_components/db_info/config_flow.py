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

from .const import (
    ALL_TRANSPORT_TYPES,
    CONF_CONNECTION_TYPE,
    CONF_DESTINATION,
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

# Human-readable labels for individual transport types
TRANSPORT_TYPE_LABELS = {
    "ICE": "ICE (Intercity-Express)",
    "EC_IC": "EC / IC (Eurocity / Intercity)",
    "IR": "IR (Interregio)",
    "REGIONAL": "RE / RB (Regionalexpress / Regionalbahn)",
    "SBAHN": "S-Bahn",
    "BUS": "Bus",
    "SCHIFF": "Schiff / Fähre",
    "UBAHN": "U-Bahn",
    "TRAM": "Straßenbahn / Tram",
    "ANRUFPFLICHTIG": "Anrufpflichtiger Verkehr",
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


def _build_options_schema(current_connection_type, current_interval):
    return vol.Schema(
        {
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
    )


class DBInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self._data = {}

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
            self._data = user_input

            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_CUSTOM:
                return await self.async_step_custom_types()

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
                    CONF_UPDATE_INTERVAL: user_input.get(CONF_UPDATE_INTERVAL, 10)
                },
            )

        return self.async_show_form(
            step_id="user",
            data_schema=_build_main_schema(valid_inputs),
            errors=errors,
        )

    async def async_step_custom_types(self, user_input=None):
        if user_input is not None:
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
                    CONF_UPDATE_INTERVAL: self._data.get(CONF_UPDATE_INTERVAL, 10)
                },
            )

        return self.async_show_form(
            step_id="custom_types",
            data_schema=_build_custom_schema(),
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

        if user_input is not None:
            self._options = user_input

            if user_input.get(CONF_CONNECTION_TYPE) == CONNECTION_CUSTOM:
                return await self.async_step_custom_types()

            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=_build_options_schema(current_connection_type, current_interval),
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
