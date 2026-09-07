"""Discovery and naming for the models this branch adds.

Vendor product names on the discovery card and on the created entry. The "not tested on real
hardware" note has no model to fire on here; it is covered with the inferred profiles that
introduce one.
"""

from homeassistant import config_entries
from homeassistant.components.bluetooth import BluetoothServiceInfo
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.ha_govee_led_ble.config_flow import _entry_title
from custom_components.ha_govee_led_ble.const import CONF_MODEL, DOMAIN, MODEL_PROFILES

# His module-local autouse fixture. Without it these tests set Bluetooth up for real, which
# raises an adapter discovery flow of its own and makes async_progress() ordering a lottery.
from tests.test_config_flow import mock_bluetooth  # noqa: F401 -- autouse fixture, used by name

SVC = BluetoothServiceInfo("Govee_H1A42_ABCD", "22:33:44:55:66:77", -60, {}, {}, [], "local")


def test_entry_titles_use_the_vendor_product_name_and_keep_the_sku():
    """The vendor's own name, on the one string a user sees before anything else works.

    "Govee H1A42" is this repository's word for the device; "Govee LED Strip Light 2" is
    Govee's. The SKU stays in parentheses because it is the only thing separating products
    that share a name -- someone with an H1A42 and an H1A43 needs two distinguishable entries.
    """
    assert _entry_title("H1A42") == "Govee LED Strip Light 2 (H1A42)"
    assert _entry_title("H61F5") == "Govee Strip Light 2 Pro (H61F5)"
    # A profile shared by two SKUs must not have its name claim one of them: H617A and H617E
    # are one object, so both fall back to `Govee <SKU>`.
    assert _entry_title("H617A") == "Govee H617A"
    assert _entry_title("H617E") == "Govee H617E"

    titles = [_entry_title(sku) for sku in MODEL_PROFILES]
    assert len(set(titles)) == len(titles), "two models would produce the same entry title"
    for sku, title in zip(MODEL_PROFILES, titles, strict=True):
        assert title.startswith("Govee "), f"{sku} title is not in the vendor's own form: {title}"
        assert title.endswith(f"({sku})") or title == f"Govee {sku}", f"{sku}: {title}"


async def test_the_discovery_card_carries_the_product_name_not_the_sku(hass: HomeAssistant):
    """The card is where the name is actually needed, and it was the one place showing a SKU.

    Setting the title only at async_create_entry meant the card said "H1A42" while the entry
    said "Govee LED Strip Light 2 (H1A42)" -- the wrong way round, since the card is what
    somebody reads to decide whether to add the thing at all.
    """
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_BLUETOOTH}, data=SVC
    )
    # Find OUR flow by handler rather than taking index 0: the bluetooth adapter raises its own
    # discovery flow, and which lands first is not ours to depend on.
    context = next(f for f in hass.config_entries.flow.async_progress() if f["handler"] == DOMAIN)["context"]

    assert context["title_placeholders"] == {"name": "Govee LED Strip Light 2 (H1A42)"}
    placeholders = result["description_placeholders"]
    assert placeholders is not None
    assert placeholders["model"] == "Govee LED Strip Light 2 (H1A42)"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Govee LED Strip Light 2 (H1A42)"
    assert result["data"] == {CONF_MODEL: "H1A42"}
