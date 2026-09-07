"""Every registered service's schema must accept what its handler reads.

A schema and a handler that disagree fail at the worst possible moment: Home Assistant
rejects the call before the handler runs, so the error names a key rather than a cause and
nothing in the integration is on the stack. `set_dreamview_group` shipped that way -- the
handler reads `enabled` and `is_rgbic`, the schema listed neither, and a caller passing the
membership list the docstring describes got

    extra keys not allowed @ data['members'][0]['enabled']

from a script that had already written "Starting..." to a dashboard.
"""

import inspect

import pytest
import voluptuous as vol

from custom_components.ha_govee_led_ble import light_services_extra
from custom_components.ha_govee_led_ble.light_services_registration import (
    _ENTITY_SERVICES,
    _RELEASE_SCHEMA,
    _SET_GROUP_SCHEMA,
)


@pytest.mark.parametrize(("name", "schema", "method", "_returns"), _ENTITY_SERVICES)
def test_every_schema_key_is_a_parameter_the_handler_accepts(name, schema, method, _returns):
    """The other direction of the same disagreement: a schema key nothing reads."""
    handler = getattr(light_services_extra._GoveeExtraServicesMixin, method, None)
    if handler is None:  # release_ble lives on the coordinator
        return
    parameters = set(inspect.signature(handler).parameters) - {"self"}
    for key in schema:
        assert str(key) in parameters, f"{name}: schema offers {key!r}, {method} does not take it"


def test_every_handler_parameter_is_offered_by_its_schema():
    """And the direction that actually bit: a handler parameter no schema exposes."""
    for name, schema, method, _returns in _ENTITY_SERVICES:
        handler = getattr(light_services_extra._GoveeExtraServicesMixin, method, None)
        if handler is None:
            continue
        signature = inspect.signature(handler)
        required = {
            parameter
            for parameter, value in signature.parameters.items()
            if parameter != "self" and value.default is inspect.Parameter.empty
        }
        offered = {str(key) for key in schema}
        assert required <= offered, f"{name}: {method} requires {required - offered}, schema offers {offered}"


def test_the_group_schema_accepts_the_membership_list_the_handler_documents():
    """`enabled: false` leaves a device out of the upload, which is the app's own toggle.

    A caller keeps ONE list of every device it knows about and flips members in and out,
    rather than rewriting the list each time. That is the shape the handler reads and the
    shape the schema has to accept.
    """
    schema = vol.Schema({**_SET_GROUP_SCHEMA})
    validated = schema(
        {
            "members": [
                {"address": "AA:BB:CC:DD:EE:01", "enabled": True, "zones": [1, 2, 3, 4, 5, 6]},
                {"address": "AA:BB:CC:DD:EE:02", "enabled": False, "zones": [1, 2, 3, 4, 5, 6]},
                {"address": "AA:BB:CC:DD:EE:03", "zones": [1, 2, 3, 4, 5, 6], "is_rgbic": False},
            ]
        }
    )

    assert [m["enabled"] for m in validated["members"]] == [True, False, True]
    assert [m["is_rgbic"] for m in validated["members"]] == [True, True, False]


def test_release_accepts_a_whole_session_and_a_clearing_zero():
    schema = vol.Schema({**_RELEASE_SCHEMA})
    assert schema({})["seconds"] == 120.0
    assert schema({"seconds": 0})["seconds"] == 0
    assert schema({"seconds": 86400})["seconds"] == 86400
    with pytest.raises(vol.Invalid):
        schema({"seconds": 86401})
