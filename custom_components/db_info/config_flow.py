import voluptuous as vol  # noqa: D100

from homeassistant import config_entries
from homeassistant.helpers.selector import (
    EntityFilterSelectorConfig,
    EntitySelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
)

from .const import CONF_DESTINATION, CONF_START, CONF_UPDATE_INTERVAL, DOMAIN


class DBInfoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):  # noqa: D101
    VERSION = 1

    async def async_step_user(self, user_input=None):  # noqa: D102
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

            return self.async_create_entry(title=title, data=user_input)

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
