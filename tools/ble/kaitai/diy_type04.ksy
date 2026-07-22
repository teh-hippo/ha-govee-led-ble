meta:
  id: diy_type04
  title: Govee H617A reassembled DIY TYPE 0x04 body — Flat DIY + Combo DIY (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body for DIY TYPE 0x04 (host concatenates the
  17-byte A3 chunks; the a3/idx/xor framing and the trailing empty 0xFF terminator
  are transport, not modelled here). Reassembled on-wire layout:
    byte[0]=01 byte[1]=<linecount> byte[2]=04 byte[3]=<FAMILY> <rest, depends on FAMILY>
  The FAMILY byte at byte[3] is read once, then the remainder is type-switched:
  FAMILY == 0xFF selects the Combo layout; any other value IS the flat family code
  and selects the Flat layout. Each layout ends in transport zero padding to the
  17-byte A3 chunk boundary (grammar-enforced all-zero), fully consuming the body.
  Encoder parity: protocol.build_flat_diy body = [family, variant, speed,
  len(palette)] + palette; protocol.build_combo body = [0xFF, variant, speed,
  len(palette)] + palette + [len(sequence)] + sequence, sequence = (FAMILY,VARIANT)
  pairs. Verified byte-exact against captured Flat and Combo bodies; captures are
  ground truth. Scene (0x02), Finger Sketch/Vibrant (0x03) and Music (0x41) bodies
  use other grammars and must not be routed here.
seq:
  - id: header
    type: govee_common::a3_header
    doc: |
      bytes[0..1], the shared A3 reassembled-body header 01 <linecount>. linecount is
      the A3 data-chunk count (never below 0x02); Flat/Combo bodies span 1-2 chunks.
      [CONFIRMED_LIVE] round-tripped in every captured Flat and Combo body.
  - id: a3_type
    contents: [0x04]
    doc: |
      byte[2] = 0x04, the A3 payload TYPE selecting the Flat/Combo DIY family.
      [CONFIRMED_LIVE]
  - id: family
    type: u1
    doc: |
      byte[3]. 0xFF selects the Combo layout; any other value IS the flat family
      code (equal to the app's internal effect-family code) and selects the Flat
      layout. Read once here and switched below. [CONFIRMED_LIVE]
  - id: body
    type:
      switch-on: family
      cases:
        0xff: combo_body
        _: flat_body
    doc: |
      Remainder after the family byte at byte[3]: combo_body when FAMILY == 0xFF,
      otherwise flat_body. [CONFIRMED_LIVE]
types:
  palette:
    doc: |
      PLEN bytes of ordered RGB triplets, sized to the parent's PLEN byte. PLEN =
      colours x 3, so repeat: eos fills the PLEN-sized substream exactly and the
      colour count is PLEN / 3.
    seq:
      - id: colours
        type: govee_common::rgb
        repeat: eos
        doc: |
          ordered RGB triplets filling the PLEN-byte palette region; count =
          PLEN / 3. [CONFIRMED_LIVE]
  family_variant:
    doc: |
      one Combo sequence entry: a (FAMILY, VARIANT) pair reusing the flat effect
      codes. The Combo SEQLEN counts these pair bytes, so SEQLEN = 2 x pairs.
    seq:
      - id: family
        type: u1
        doc: |
          effect family code, reuses the flat FAMILY value. [CONFIRMED_LIVE]
      - id: variant
        type: u1
        doc: |
          family-specific VARIANT selector for this chained effect. [CONFIRMED_LIVE]
  flat_body:
    doc: |
      Flat DIY (FAMILY != 0xFF). After the family byte at byte[3] the body is:
        byte[4]=VARIANT byte[5]=SPEED byte[6]=PLEN byte[7 .. 7+PLEN-1]=palette
      then transport zero padding to the A3 chunk boundary. Mirrors
      protocol.build_flat_diy body = [family, variant, speed, len(palette)] +
      palette (the family byte is the parent's byte[3]).
    seq:
      - id: variant
        type: u1
        doc: |
          byte[4], family-specific VARIANT selector (no global formula), raw.
          [CONFIRMED_LIVE]
      - id: speed
        type: u1
        doc: |
          byte[5], SPEED 0-100 (default 0x32 = 50). [CONFIRMED_LIVE]
      - id: plen
        type: u1
        doc: |
          byte[6], PLEN = palette length in bytes = colours x 3. [CONFIRMED_LIVE]
      - id: palette
        type: palette
        size: plen
        doc: |
          byte[7 ..], PLEN bytes of ordered RGB triplets (PLEN / 3 colours).
          [CONFIRMED_LIVE]
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: |
          transport zero padding to the 17-byte A3 chunk boundary (includes the
          empty 0xFF terminator chunk); grammar-enforced all-zero. [CONFIRMED_LIVE]
  combo_body:
    doc: |
      Combo DIY (FAMILY == 0xFF). After the 0xFF family byte at byte[3] the body is:
        byte[4]=VARIANT byte[5]=SPEED byte[6]=PLEN byte[7 .. 7+PLEN-1]=palette
        byte[7+PLEN]=SEQLEN <SEQLEN bytes of (FAMILY,VARIANT) pairs>
      then transport zero padding to the A3 chunk boundary. SEQLEN = 2 x
      effect_count (1-4 effects). Mirrors protocol.build_combo body = [0xFF,
      variant, speed, len(palette)] + palette + [len(sequence)] + sequence.
    seq:
      - id: variant
        type: u1
        doc: |
          byte[4], shared VARIANT for the chained effects, raw. [CONFIRMED_LIVE]
      - id: speed
        type: u1
        doc: |
          byte[5], shared SPEED 0-100 (0x33 = 51 in the Combo captures).
          [CONFIRMED_LIVE]
      - id: plen
        type: u1
        doc: |
          byte[6], PLEN = shared palette length in bytes = colours x 3.
          [CONFIRMED_LIVE]
      - id: palette
        type: palette
        size: plen
        doc: |
          byte[7 ..], PLEN bytes of ordered RGB triplets (PLEN / 3 colours) shared
          by every chained effect. [CONFIRMED_LIVE]
      - id: seqlen
        type: u1
        doc: |
          byte[7+PLEN], SEQLEN = sequence length in bytes = 2 x effect_count.
          [CONFIRMED_LIVE]
      - id: pairs
        type: family_variant
        repeat: expr
        repeat-expr: seqlen / 2
        doc: |
          SEQLEN / 2 chained (FAMILY, VARIANT) effect pairs, each reusing the flat
          effect codes. [CONFIRMED_LIVE]
      - id: padding
        type: u1
        valid: 0
        repeat: eos
        doc: |
          transport zero padding to the 17-byte A3 chunk boundary (includes the
          empty 0xFF terminator chunk); grammar-enforced all-zero. [CONFIRMED_LIVE]
