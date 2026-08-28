"""Home Assistant entity action for saved custom effects."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import ServiceValidationError

from custom_components.ha_govee_led_ble.const import DOMAIN
from custom_components.ha_govee_led_ble.effect_backend import EffectBackend
from custom_components.ha_govee_led_ble.effect_domain import LibraryItem, PaintedEffect
from custom_components.ha_govee_led_ble.effect_services import (
    SERVICE_APPLY_CUSTOM_EFFECT,
    async_register_effect_services,
)
from custom_components.ha_govee_led_ble.effect_storage import LibrarySnapshot
from custom_components.ha_govee_led_ble.light import GoveeBLELight


def test_service_registration_uses_home_assistant_entity_targeting(
    hass: HomeAssistant,
) -> None:
    with patch(
        "custom_components.ha_govee_led_ble.effect_services.service.async_register_platform_entity_service"
    ) as register:
        async_register_effect_services(hass, MagicMock())

    register.assert_called_once()
    assert register.call_args.args[:3] == (
        hass,
        DOMAIN,
        SERVICE_APPLY_CUSTOM_EFFECT,
    )
    assert register.call_args.kwargs["entity_domain"] is Platform.LIGHT
    assert register.call_args.kwargs["func"] == "async_apply_custom_effect"
    assert register.call_args.kwargs["supports_response"] is SupportsResponse.OPTIONAL


@pytest.mark.parametrize("reference", ["name", "id"])
async def test_entity_action_applies_saved_effect_and_returns_deployment(
    mock_coordinator,
    reference: str,
) -> None:
    item = LibraryItem.new(
        "Paint",
        PaintedEffect("clockwise", 50, 100, (None,) * 15),
    )
    deployment = SimpleNamespace(
        to_public_dict=MagicMock(
            return_value={
                "operation_id": "11111111-1111-1111-1111-111111111111",
                "phase": "confirmed",
            }
        )
    )
    application = SimpleNamespace(
        library_snapshot=MagicMock(return_value=LibrarySnapshot((item,))),
        get_saved_effect=MagicMock(return_value=item),
    )

    @asynccontextmanager
    async def saved_effect_for_apply(*_args, **_kwargs):
        yield item

    application.saved_effect_for_apply = saved_effect_for_apply
    apply_saved = AsyncMock(return_value=deployment)
    preview = SimpleNamespace(async_supersede_device=AsyncMock())
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=application,
            engine=SimpleNamespace(async_apply_saved=apply_saved),
            preview=preview,
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    response = await entity.async_apply_custom_effect(
        effect=item.name if reference == "name" else None,
        effect_id=str(item.id) if reference == "id" else None,
    )

    assert response["phase"] == "confirmed"
    preview.async_supersede_device.assert_awaited_once_with(
        "entry-a",
        reason="home_assistant_control",
    )
    apply_saved.assert_awaited_once()
    assert apply_saved.await_args is not None
    assert apply_saved.await_args.kwargs["operation_id"] is not None


@pytest.mark.parametrize(
    ("effect", "effect_id"),
    [(None, None), ("Paint", "11111111-1111-1111-1111-111111111111")],
)
async def test_entity_action_requires_one_effect_reference(
    mock_coordinator,
    effect: str | None,
    effect_id: str | None,
) -> None:
    backend = cast(
        EffectBackend,
        SimpleNamespace(
            application=SimpleNamespace(
                library_snapshot=MagicMock(return_value=LibrarySnapshot(())),
            ),
            preview=SimpleNamespace(async_supersede_device=AsyncMock()),
            device_cache=SimpleNamespace(get=MagicMock(return_value=None)),
        ),
    )
    entity = GoveeBLELight(
        mock_coordinator,
        config_entry_id="entry-a",
        effect_backend=backend,
    )

    with pytest.raises(ServiceValidationError) as error:
        await entity.async_apply_custom_effect(
            effect=effect,
            effect_id=effect_id,
        )

    assert error.value.translation_key == "invalid_custom_effect"
