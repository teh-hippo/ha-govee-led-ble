meta:
  id: h6182_diy_body
  title: Govee H6182 legacy palette DIY
  endian: be
  imports:
    - h6181_diy_body
doc: |
  SPECULATIVE H6182 legacy A1 command-02 palette contract.
  Selector, family, variant, speed, palette byte length, RGB triples,
  component byte length and family/variant pairs share the whole-strip
  palette codec. Families 0/1/2 fade, jump and blink; FF mixes at most
  four components. Palettes contain one to eight colours; speed is 0..100.
  Later Pact controllers use the shared A3/04 palette body instead.
  Neither delivered bytes nor optimistic state confirm hardware support.
seq:
  - id: body
    type: h6181_diy_body
