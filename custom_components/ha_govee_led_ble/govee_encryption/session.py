"""Evidence-selected, fail-closed encryption for one BLE connection at a time."""

import asyncio
import os
import warnings
from typing import Any

from ..transport import ENCRYPTION_UUID, WRITE_UUID, xor_checksum
from . import (
    MIN_MTU,
    GoveeCryptoError,
    build_v1_handshake,
    build_v2_handshake,
    parse_v1_handshake,
    parse_v2_handshake,
    parse_wire,
    seal,
    unseal,
    v1_transform,
)

HANDSHAKE_TIMEOUT = 6.0  # EncryptionManager: both key and confirmation waits.


class GoveeEncryptionSession:
    def __init__(self) -> None:
        self.version = 0
        self.required_version = 0
        self._selection_failed = False
        self.ready = False
        self.last_result = "not_selected"
        self.rejected_frames = 0
        self._handshake: asyncio.Future[Any] | None = None
        self._opcode = 0
        self._key: bytes | None = None
        self._client_iv: bytes | None = None
        self._device_iv: bytes | None = None
        self._counter = 2
        self._received_counter = 0
        self._mtu = 0
        self._generation = 0

    @property
    def active(self) -> bool:
        return self.ready and self.version != 0

    def reset(self) -> None:
        self._generation += 1
        self.ready = False
        if self._handshake is not None and not self._handshake.done():
            self._handshake.set_exception(GoveeCryptoError("session_reset"))
            self._handshake.exception()
        self._handshake = None
        self._opcode = 0
        self._key = self._client_iv = self._device_iv = None
        self._counter, self._received_counter = 2, 0
        self._mtu = 0

    async def async_select(self, client: Any, *, advertised: bool) -> None:
        self.reset()
        generation = self._generation
        self.version = 0
        if advertised and not self.required_version:
            self.required_version = 1
        try:
            # Enumerate discovered services: absence alone never causes a read or probe.
            characteristic = next(
                (c for service in client.services for c in service.characteristics if c.uuid == ENCRYPTION_UUID), None
            )
            if characteristic is None:
                if self._selection_failed:
                    raise GoveeCryptoError("previous_selection_failed")
                self.version = self.required_version or (1 if advertised else 0)
            else:
                data = await client.read_gatt_char(ENCRYPTION_UUID)
                if not isinstance(data, (bytes, bytearray)):
                    raise GoveeCryptoError("invalid_marker")
                marker = parse_wire("Marker", bytes(data))
                if marker.format not in (1, 2) or marker.version not in (0, 1, 2):
                    raise GoveeCryptoError("invalid_marker")
                # Version zero permits plaintext only without positive encryption evidence.
                self.version = marker.version or self.required_version
                self._selection_failed = False
            if self.version:
                self.required_version = self.version
            if generation != self._generation or not client.is_connected:
                raise GoveeCryptoError("session_reset")
            self.ready = self.version == 0
            self.last_result = "plaintext" if self.ready else "selected"
        except asyncio.CancelledError:
            self._selection_failed = True
            self.last_result = "cancelled"
            self.reset()
            raise
        except Exception:
            self._selection_failed = True
            self.last_result = "selection_failed"
            self.reset()
            raise GoveeCryptoError("encryption_selection_failed") from None

    async def _exchange(self, client: Any, opcode: int, packet: bytes) -> Any:
        generation = self._generation
        self._opcode = opcode
        future = self._handshake = asyncio.get_running_loop().create_future()
        async with asyncio.timeout(HANDSHAKE_TIMEOUT):
            await client.write_gatt_char(WRITE_UUID, packet, response=False)
            result = await future
            if generation != self._generation or not client.is_connected:
                raise GoveeCryptoError("session_reset")
            return result

    async def async_negotiate(self, client: Any) -> None:
        if self.ready and self.version == 0:
            return
        try:
            if self.version == 1:
                reply = await self._exchange(client, 1, build_v1_handshake(1))
                key = reply.body
                await self._exchange(client, 2, build_v1_handshake(2))
                self._key = key
            elif self.version == 2:
                generation = self._generation
                with warnings.catch_warnings():
                    warnings.simplefilter("ignore")
                    mtu = client.mtu_size
                    # HA's wrapper exposes BlueZ's backend. Its MTU is a cached
                    # default (23) until AcquireWrite/AcquireNotify asks the link.
                    if type(mtu) is not int or mtu < MIN_MTU:
                        acquire_mtu = getattr(getattr(client, "_backend", None), "_acquire_mtu", None)
                        if callable(acquire_mtu):
                            async with asyncio.timeout(HANDSHAKE_TIMEOUT):
                                await acquire_mtu()
                            mtu = client.mtu_size
                if generation != self._generation or not client.is_connected:
                    raise GoveeCryptoError("session_reset")
                if type(mtu) is not int or mtu < MIN_MTU:
                    raise GoveeCryptoError("v2_fragmentation_unsupported")
                self._mtu = mtu
                self._client_iv = os.urandom(8)
                self._device_iv, self._key = await self._exchange(client, 0x11, build_v2_handshake(self._client_iv))
            else:
                raise GoveeCryptoError("session_not_selected")
            if not client.is_connected:
                raise GoveeCryptoError("disconnected_during_negotiation")
            self.ready = True
            self.last_result = "encrypted"
        except asyncio.CancelledError:
            self.last_result = "cancelled"
            self.reset()
            raise
        except Exception as err:
            self.last_result = "negotiation_timeout" if isinstance(err, TimeoutError) else "negotiation_failed"
            self.reset()
            raise GoveeCryptoError(self.last_result) from None
        finally:
            self._handshake = None
            self._opcode = 0

    def encode(self, packet: bytes) -> bytes:
        if not self.ready:
            raise GoveeCryptoError("session_not_ready")
        if self.version == 0:
            return packet
        if self._key is None:
            raise GoveeCryptoError("session_not_ready")
        if self.version == 1:
            return v1_transform(packet, self._key, encrypt=True)
        if self._client_iv is None:
            raise GoveeCryptoError("session_not_ready")
        if len(packet) + 20 > self._mtu - 3:
            raise GoveeCryptoError("v2_fragmentation_unsupported")
        frame = seal(packet, self._client_iv, self._key, self._counter)
        self._counter += 1
        return frame

    def decode(self, frame: bytes) -> bytes | None:
        try:
            if not self.ready:
                if (future := self._handshake) is None or future.done():
                    return None
                if self.version == 1:
                    reply = parse_v1_handshake(frame)
                    if reply.opcode != self._opcode:
                        # A duplicate key response is not confirmation of the next phase.
                        self.rejected_frames += 1
                        return None
                    future.set_result(reply)
                elif self.version == 2:
                    future.set_result(parse_v2_handshake(frame))
                return None
            if self.version == 0:
                return frame
            if self._key is None:
                raise GoveeCryptoError("session_not_ready")
            if self.version == 1:
                plain = v1_transform(frame, self._key, encrypt=False)
                if len(plain) != 20 or xor_checksum(plain):
                    raise GoveeCryptoError("invalid_frame")
                return plain
            if self._device_iv is None:
                raise GoveeCryptoError("session_not_ready")
            counter, plain = unseal(frame, self._device_iv, self._key)
            if counter <= self._received_counter:
                raise GoveeCryptoError("replayed_frame")
            self._received_counter = counter
            return plain
        except GoveeCryptoError:
            self.rejected_frames += 1
            if (future := self._handshake) is not None and not future.done():
                future.set_exception(GoveeCryptoError("invalid_handshake"))
                future.exception()
            return None

    def diagnostics(self) -> dict[str, Any]:
        return {
            "active": self.active,
            "ready": self.ready,
            "version": self.version,
            "last_result": self.last_result,
            "rejected_frames": self.rejected_frames,
        }
