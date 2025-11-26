import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntityFilterSelectorConfig,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import CONF_DESTINATION, CONF_START, CONF_UPDATE_INTERVAL, DOMAIN


class DBInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Config flow for DB Info integration."""

    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            start_entity = user_input[CONF_START]
            destination_entity = user_input[CONF_DESTINATION]

            # Namen der Entities holen (z.B. Dieter, Zuhause)
            start_state = self.hass.states.get(start_entity)
            destination_state = self.hass.states.get(destination_entity)
            start_name = start_state.name
            destination_name = destination_state.name

            title = f"{start_name} → {destination_name}"

            # Speichere nur Start & Ziel in data, Intervall in options
            return self.async_create_entry(
                title=title,
                data={
                    CONF_START: user_input[CONF_START],
                    CONF_DESTINATION: user_input[CONF_DESTINATION],
                },
                options={
                    CONF_UPDATE_INTERVAL: user_input.get(CONF_UPDATE_INTERVAL, 10)
                },
            )

        all_persons = self.hass.states.async_all("person")

        # only persons with coordinates
        valid_persons = [
            p.entity_id
            for p in all_persons
            if "latitude" in p.attributes and "longitude" in p.attributes
        ]

        valid_inputs = valid_persons + [
            z.entity_id for z in self.hass.states.async_all("zone")
        ]

        if not valid_inputs:
            errors["base"] = "No Enities with coordinates found"

        schema = vol.Schema(
            {
                vol.Required(CONF_START): EntitySelector(
                    EntityFilterSelectorConfig(include_entities=valid_inputs)
                ),
                vol.Required(CONF_DESTINATION): EntitySelector(
                    EntityFilterSelectorConfig(include_entities=valid_inputs)
                ),
                vol.Optional(CONF_UPDATE_INTERVAL, default=10): NumberSelector(
                    NumberSelectorConfig(min=1, max=60, mode=NumberSelectorMode.BOX)
                ),
            }
        )

        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return DBInfoOptionsFlowHandler(config_entry)


class DBInfoOptionsFlowHandler(config_entries.OptionsFlow):
    """Handle options for existing entries."""

    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(
                            CONF_UPDATE_INTERVAL,
                            self.config_entry.data.get(CONF_UPDATE_INTERVAL, 10),
                        ),
                    ): NumberSelector(
                        NumberSelectorConfig(
                            min=1,
                            max=60,
                            mode=NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )
