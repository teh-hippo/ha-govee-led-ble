meta:
  id: h6199_status_query
  title: Govee H6199 "aa" status-query envelope (decode-only)
  endian: le
doc: |
  H6199 phone-to-light status queries from the attributable iPhone connect burst
  in h6199-aa40.pcap. This model is independent from both the H617A grammar and
  h6199_status_reply: a query and its reply share the register byte but do not
  necessarily share a body shape.

  The hardware query is the observed exception to the all-zero query body. It
  carries selector 0x03 at frame offset 2; firmware, power, identity and the two
  subordinate-version queries carry zero-filled body windows.
seq:
  - id: header
    contents: [0xaa]
    doc: 'H6199 status-query header at frame offset 0'
  - id: domain
    type: u1
    enum: query_domain
    doc: 'H6199 queried register at frame offset 1'
  - id: body
    size: 17
    type:
      switch-on: domain
      cases:
        'query_domain::power': zero_body
        'query_domain::brightness': zero_body
        'query_domain::colour_mode': zero_body
        'query_domain::firmware': zero_body
        'query_domain::hardware': hardware_query_body
        'query_domain::identity': zero_body
        'query_domain::subordinate_20': zero_body
        'query_domain::subordinate_21': zero_body
        'query_domain::display_setting': display_setting_query_body
        'query_domain::relative_brightness': relative_brightness_query_body
    doc: 'H6199 query body at frame offsets 2..18, selected by the queried register'
  - id: checksum
    type: u1
    doc: 'raw XOR checksum byte at frame offset 19; validated by the fixture runner'
enums:
  query_domain:
    0x01: power
    0x04: brightness
    0x05: colour_mode
    0x06: firmware
    0x07: hardware
    0x14: identity
    0x20: subordinate_20
    0x21: subordinate_21
    0xa9: display_setting
    0xae: relative_brightness
  display_setting:
    0x00: white_balance
    0x0a: blank_screen
types:
  zero_body:
    seq:
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
        doc: 'all-zero H6199 query body; grammar-enforced across the captured power, brightness, colour-mode, firmware, identity and subordinate-version queries'
  hardware_query_body:
    seq:
      - id: selector
        contents: [0x03]
        doc: 'H6199 hardware-version query selector at frame offset 2'
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
        doc: 'all-zero remainder after the H6199 hardware query selector'
  display_setting_query_body:
    seq:
      - id: setting
        type: u1
        enum: display_setting
        doc: |
          which 0xa9 display setting is requested, at frame offset 2.
          Captured as 0x00 immediately before the white-balance reply and 0x0a immediately
          before the blank-screen reply.
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
        doc: 'all-zero remainder after the H6199 display-setting selector'
  relative_brightness_query_body:
    seq:
      - id: selector
        contents: [0x01]
        doc: |
          relative-brightness query selector at frame offset 2, captured
          immediately before the device replied with its four edge percentages.
      - id: zeros
        type: u1
        valid: 0
        repeat: eos
        doc: 'all-zero remainder after the relative-brightness query selector'
