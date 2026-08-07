meta:
  id: h6199_wifi_provision
  title: Govee H6199 "a1 11" Wi-Fi provisioning frame (decode-only)
  endian: be
doc: |
  One 20-byte write of the H6199's Wi-Fi provisioning sequence, modelled from captures of
  the Govee Home iOS app driving a DreamView T1. Vendor-generated 48-, 49- and 65-byte
  bodies exercise three, four and five data frames respectively.

  A provisioning push is a SEQUENCE, not a frame: a header frame carrying the number of data
  frames, then that many data frames each holding 16 bytes of the body, then an empty frame
  indexed 0xff. The reassembled body is modelled by h6199_wifi_body.

  The device answers twice, on two different channels. It acknowledges the write within
  milliseconds on this same a1 11 register with an all-zero payload, and then reports the
  outcome of the association attempt about eleven seconds later on ee 11. Both values of
  that outcome have now been observed on our own hardware: 0x01 after pushing a network
  invented to be impossible, and 0x00 after pushing credentials for a network that existed,
  with an independent observer confirming the light had joined it.

  EVERY CAPTURED SEQUENCE USES FABRICATED CREDENTIALS. The fixtures carry an invented SSID
  and passphrase, in the same spirit as this project's fake BLE addresses: real structure,
  invented values. No real network's credentials are committed here, and none should be.
seq:
  - id: header
    contents: [0xa1]
    doc: 'H6199 multi-part upload header at frame offset 0'
  - id: sub_opcode
    type: u1
    valid: 0x11
    doc: |
      H6199 upload sub-register at frame offset 1, 0x11 for Wi-Fi
      provisioning. This byte is what makes 0xA1 a family rather than a single command, and
      it is repeated on every frame of the sequence rather than appearing once in a header.
  - id: index
    type: u1
    doc: |
      H6199 frame index at frame offset 2. 0x00 is the header frame, 0x01
      upwards are data frames in order, and 0xff is a dedicated empty terminator that is
      always sent regardless of whether the last data frame was full.

      That terminator is NOT the H617A's 0xA3 behaviour, where the final data chunk may
      itself be numbered 0xff and carry real bytes. The two fragmenters differ, which is why
      this model is written from H6199 captures rather than derived from the other one.
  - id: payload
    size: 16
    doc: 'H6199 frame payload at offsets 3..18; on the header frame byte 0 is the data-frame count and the rest is zero, and on the terminator the whole window is zero'
  - id: checksum
    type: u1
    doc: 'raw XOR checksum byte at frame offset 19; validated by the fixture runner'
instances:
  is_header:
    value: index == 0
    doc: 'the first frame of a sequence, whose payload byte 0 states how many data frames follow'
  is_terminator:
    value: index == 0xff
    doc: 'the empty closing frame of a sequence'
  data_frame_count:
    value: payload[0]
    if: index == 0
    doc: |
      number of data frames the header announces. Captured as 3, 4 and 5
      for 48-, 49- and 65-byte bodies, exactly ceil(body_length / 16). Each sequence then
      carried precisely that many indexed data frames before the empty terminator.
