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
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}

        if user_input is not None:
            start_entity = user_input[CONF_START]
            destination_entity = user_input[CONF_DESTINATION]

            start_state = self.hass.states.get(start_entity)
            destination_state = self.hass.states.get(destination_entity)
            start_name = start_state.name if start_state is not None else start_entity
            destination_name = (
                destination_state.name
                if destination_state is not None
                else destination_entity
            )

            title = f"{start_name} → {destination_name}"

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

        # only persons with location and all zones
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
        return DBInfoOptionsFlowHandler()


class DBInfoOptionsFlowHandler(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        current_interval = self.config_entry.options.get(
            CONF_UPDATE_INTERVAL,
            self.config_entry.data.get(CONF_UPDATE_INTERVAL, 10),
        )

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_UPDATE_INTERVAL, default=current_interval
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=60, mode=NumberSelectorMode.BOX)
                )
            }
        )

        return self.async_show_form(step_id="init", data_schema=schema)
