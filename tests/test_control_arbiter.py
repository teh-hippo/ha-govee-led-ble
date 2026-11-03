"""Per-device BLE control arbitration tests."""

import asyncio

from custom_components.ha_govee_led_ble.control_arbiter import BLEControlArbiter, ControlIntent, LatestRequests


async def test_control_arbiter_prioritises_waiters_reenters_and_skips_background():
    arbiter = BLEControlArbiter()
    order: list[ControlIntent] = []

    async def contender(intent: ControlIntent) -> None:
        async with arbiter.hold(intent):
            order.append(intent)
            await asyncio.sleep(0)

    async with arbiter.hold(ControlIntent.BACKGROUND):
        async with arbiter.hold(ControlIntent.PREVIEW):
            assert arbiter.current_task_intent is ControlIntent.PREVIEW
        tasks = [
            asyncio.create_task(contender(ControlIntent.PREVIEW)),
            asyncio.create_task(contender(ControlIntent.APPLY)),
            asyncio.create_task(contender(ControlIntent.USER)),
        ]
        await asyncio.sleep(0)
        async with arbiter.hold(ControlIntent.BACKGROUND, wait=False) as acquired:
            assert acquired is True

        async def separate_background() -> bool:
            async with arbiter.hold(ControlIntent.BACKGROUND, wait=False) as background_acquired:
                return background_acquired

        assert await asyncio.create_task(separate_background()) is False

    await asyncio.gather(*tasks)
    assert order == [ControlIntent.USER, ControlIntent.APPLY, ControlIntent.PREVIEW]


async def test_control_arbiter_accepts_new_preview_during_foreground_intent():
    arbiter = BLEControlArbiter()

    async with arbiter.hold(ControlIntent.USER):
        admission = arbiter.admit_preview()

    assert admission.is_current is True


async def test_latest_requests_sends_first_and_newest_in_order():
    requests = LatestRequests()
    release = asyncio.Event()
    sent: list[str] = []

    async def send(value: str) -> None:
        sent.append(value)
        if value == "a1":
            await release.wait()

    tasks = [
        asyncio.create_task(requests.run(key, lambda value=value: send(value)))
        for key, value in (("a", "a1"), ("a", "a2"), ("b", "b1"), ("a", "a3"))
    ]
    await asyncio.sleep(0)
    assert sent == ["a1"]
    release.set()
    await asyncio.gather(*tasks)

    assert sent == ["a1", "b1", "a3"]
