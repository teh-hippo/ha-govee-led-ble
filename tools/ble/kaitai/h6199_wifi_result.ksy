meta:
  id: h6199_wifi_result
  title: Govee H6199 "ee 11" Wi-Fi association result (decode-only)
  endian: be
doc: |
  The H6199's own report of how a Wi-Fi provisioning attempt ended, sent unprompted about
  eleven seconds after the a1 11 sequence it answers. Distinct from the a1 11 write-ack,
  which arrives within milliseconds and only says the frames were structurally accepted.

  This family was invisible to our decoder for weeks. Its frame allowlist named the headers
  we already understood, so 0xEE was dropped, and a provisioning capture decoded as a write
  that was acknowledged and never answered. That read as the device ignoring the request
  when it had in fact replied to say it failed, and the frame had been sitting in the
  captures the whole time. A filter keyed on what you already recognise hides exactly the
  traffic that would teach you something.

  Both status values have now been produced deliberately on our own hardware. A network
  invented to be impossible gave 0x01. Several fabricated networks that existed gave 0x00,
  with UniFi independently confirming 2.4 GHz association even though the client had no IP
  on that VLAN and retained only its previous-subnet address as history. The result therefore
  does not require DHCP, routed connectivity or cloud reach.
seq:
  - id: header
    contents: [0xee]
    doc: 'H6199 device-initiated header at frame offset 0'
  - id: sub_opcode
    type: u1
    valid: 0x11
    doc: 'register the report concerns at frame offset 1, 0x11 being Wi-Fi provisioning, matching the register that was written'
  - id: status
    type: u1
    enum: outcome
    doc: |
      association outcome at frame offset 2. Captured as 0x01 after pushing
      a deliberately non-existent SSID, and as 0x00 after pushing working credentials.

      UniFi later observed 0x00 attempts associated to the intended SSID without obtaining a
      VLAN IP. That rules out DHCP, internet and cloud reach as prerequisites. The strongest
      supported reading is successful Wi-Fi association.
  - size: 16
    doc: Unmodelled bytes between the association status and checksum.
  - id: checksum
    type: u1
    doc: 'raw XOR checksum byte at frame offset 19; validated by the fixture runner'
enums:
  outcome:
    0x00: associated
    0x01: not_connected
