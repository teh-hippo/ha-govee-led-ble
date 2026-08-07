meta:
  id: h6199_wifi_body
  title: Govee H6199 Wi-Fi provisioning body, reassembled from a1 11 frames
  endian: be
doc: |
  The payload of an H6199 Wi-Fi provisioning push, as it appears once the data frames of an
  a1 11 sequence are concatenated in index order. See h6199_wifi_provision for the framing.

  The layout was first read out of the vendor Android app and then confirmed against wire
  bytes. The original 49-byte body exposed two trailing bytes that had been mistaken for
  padding. Later vendor captures vary only fabricated SSID length and prove the same layout
  at 48 and 65 bytes, crossing both neighbouring 16-byte frame-count boundaries.

  The bytes are UNSIGNED AND UNAUTHENTICATED. There is no MAC, hash or key anywhere in this
  body; the only transform applied to the endpoint URL is its length prefix. That was read
  at the construction site in the vendor app and is consistent with every capture.

  THE CREDENTIALS ARE IN CLEAR. Anything within BLE range of an unpaired device can read a
  provisioning push off the air. The fixtures here therefore use an invented network, and
  tools/ble/decode_govee.py withholds this body from decoded output unless explicitly asked.
seq:
  - id: ssid_len
    type: u1
    doc: 'length in bytes of the SSID that follows, at body offset 0'
  - id: ssid
    size: ssid_len
    type: str
    encoding: UTF-8
    doc: 'network name, length-prefixed rather than terminated'
  - id: password_len
    type: u1
    doc: |
      length in bytes of the passphrase that follows. An open network is
      sent as a single zero here with no passphrase bytes, which is why this cannot be read
      as a fixed-width field.
  - id: password
    size: password_len
    type: str
    encoding: UTF-8
    doc: 'passphrase in clear'
  - id: run_mode
    type: u1
    doc: |
      app environment selector, captured as 0x00. Read in the vendor app as a
      build-time constant choosing between release and internal backends rather than
      anything per-device. No capture varies it, because no capture has been taken from a
      non-release build, so it stays inferred.
  - id: tz_hour
    type: u1
    doc: |
      whole hours of the phone's UTC offset. Captured as 10 in a UTC+10
      zone, which is what checked the alignment of this whole run of single bytes rather
      than merely their shape: a layout off by one here would have put 10 somewhere else.
  - id: iot_version
    type: u1
    doc: 'IoT backend version selector, captured as 0x00 and never varied; read in the vendor app as a build constant echoed later as an HTTP header'
  - id: tz_minute
    type: u1
    doc: |
      remaining minutes of the phone's UTC offset, captured as 0. Separate
      from tz_hour and NOT adjacent to it, which is the detail a layout guessed from field
      names would get wrong: iot_version sits between them.
  - id: api_len
    type: u2
    doc: 'length of the endpoint URL, BIG-endian, in a frame family that is otherwise little-endian'
  - id: api
    size: api_len
    type: str
    encoding: UTF-8
    doc: |
      the cloud endpoint the device is told to use, captured as
      https://device.govee.com. The app never sends a free-form value: it selects one of six
      compiled-in URLs using a support level the DEVICE reports over aa ab, and ours reports
      the level that selects this one. Nothing validates it, and it is not signed, so the
      field is a lever on where the device checks in even though the app never treats it as
      one.

      A controlled same-length endpoint was pushed on  and honoured immediately.
      The H6199 accepted a self-signed TLS certificate and sent six empty-body POST retries
      to /device/v1/base/config. The query carried device, SKU and Wi-Fi-version keys; their
      values are private and not fixtures. This disproves both a compiled-host replacement
      and certificate pinning. The production URL was restored without proxying its response
      or handling the device credentials it may return.
  - id: matter_wifi_flag
    type: u1
    doc: |
      captured as 0x00 and never varied. Read in the vendor app as set only by
      the Matter pairing flow, and this SKU has no Matter, so it is expected to be inert
      here. Named rather than left opaque because the write side names it and the value is
      consistent with that reading; it is inferred because no H6199 capture varies it.
  - id: security_type
    type: u1
    doc: |
      captured as 0x00. Read in the vendor app as meaning "work it out yourself"
      for a network the app picked from a scan, with non-zero values only for a manually
      typed hidden SSID. Our captures were manual entry forced by an offline phone and still
      carried 0x00, so the value is consistent with the reading but not isolated by it.

      These last two bytes are ALSO the reason this body is 49 bytes. The vendor code we
      read appends them only on one branch, and that branch's condition is false in our
      captures, yet the bytes are present on the wire. The wire wins and the encoder always
      sends them; the predicate that selects them is an honest unknown.
