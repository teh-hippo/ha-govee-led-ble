meta:
  id: scene_body
  title: Govee H617A reassembled scene / rgbicv2 record-container body (decode-only)
  endian: le
  imports:
    - govee_common
doc: |
  The reassembled 0xA3 multi-frame body (host reassembles the 17-byte chunks; the
  framing/terminator is transport, not modelled here). On-wire layout:
    01 <linecount> <scene_type> <record_count> [<rec_len> <rec_data>]... <zero padding>
  Models scene_type 2 (rgbicv2) bodies only; other A3 bodies (music 0x41,
  Flat/Sketch/Vibrant 0x03) use different grammars and must not be routed here.

  VENDOR NAME: scene_type 2 is the vendor's MULTI_V2_NEW_SCENES. See
  govee_common::a3_header for why that name must always be quoted against the wire
  commByte and never against a class suffix.
  Every field carries exactly one evidence tag in its doc. The vocabulary and what
  each tag claims are defined once in evidence_lint.py, which also enforces them;
  do not restate them here.

  THE RECORD BODY IS THE WORKSHOP LAYER RECORD. This spec
  used to carry its own half-decoded record with an opaque trailing blob and a cluster
  of INFERRED placeholders (flags/record_type/val1/val2/r5/bright_count). That record is
  byte-for-byte the Workshop layer record, which workshop_body.ksy had already isolated
  field by field, so both specs now share govee_common::effect_layer and the placeholders
  are retired. Under the shared names: flags = applied_area, record_type = select_type,
  val1/val2 = select_param_1/2, r5 = layer_flags, bright_count = brightness_block_count,
  the old six "brightness" bytes = r7..r12, and the opaque tail = direction_distribution,
  colour_speed, colour_retention, colour_count, the M-colour palette, two 3-byte movement
  sub-blocks and the priority byte. The identity
    record_len == 16 + 6*(brightness_block_count - 1) + 3*colour_count + 7
  holds 191/191 across every type-2 record in the frozen catalogue and byte-exact against
  captured Aurora, Forest, Christmas, Bloom, Glacier and Fire bodies, whose palettes decode
  to the colours those effects visibly show. A wider re-run over a 27-SKU third-party
  archive once extended the tested range to brightness_block_count 1..3 and colour_count
  1..16; that archive was retired on , so the extension is recorded as observed
  history. The identity itself never depended on it: it holds against the captured bodies
  and the whole local catalogue, which are both still here.

  WHAT THE CATALOGUE'S moveIn / moveAll ACTUALLY ARE. They are the speed byte of the two
  movement sub-blocks: moveIn is selected_area_movement.speed and moveAll is
  overall_movement.speed, which is why they sit 5 and 2 bytes from the end of a record.
  The editor's single Speed slider writes the scene's per-page option-list value, indexed
  by slider position, into those bytes, and additionally moves colour_speed in scenes whose
  effect cycles colour. Confirmed live  on Christmas 2189, Bloom 2228, Glacier
  2175, Fire 2171, Winter 2170 and Moonlight 2177, every predicted byte and value exact.

  THE COMPLETE CONFIG-BLOCK MAPPING. One catalogue config
  block is ONE 4-stop UI control, and every list it carries is a SPEED. Selecting slider
  index i writes, into the record named by that block's page:

    moveIn[i]                  -> selected_area_movement.speed   (record_end - 5)
    moveAll[i]                 -> overall_movement.speed         (record_end - 2)
    color[i]                   -> colour_speed (r14)
    bright[k].brightValue[i]   -> brightness_blocks[k].brightness_speed (r10)

  A block may carry any subset of those four keys, and the whole subset moves together on
  one slider index, which is why they share a single defaultIndex. moveIn/moveAll are
  END-relative and colour_speed/brightness_speed are START-relative, which is exactly why
  an end-relative-only locator never found the last two. Christmas 2189 proves the model in
  one shot: three config blocks over three records, eight keys in total, and moving the one
  slider changed EXACTLY eight bytes, each to the exact catalogue value, on both the 3->0
  and 0->1 transitions, with a byte-identical A/B/A restore.

  THERE IS NO SEPARATE SCENE BRIGHTNESS BYTE. The long-running hunt for one was chasing a
  field that does not exist. Govee's key is named bright, but it addresses
  brightness_speed, the Brightness CHANGING Speed. An offline sweep had already scored that
  location best and discarded it for being "semantically wrong". Device brightness is a
  separate concern entirely and never rewrites a scene body: moving it emits only
  33 04 <percent> (live , and re-confirmed  where aa 04 read back 5 at
  5% and 7 at 7%).

  CATALOGUE PARAM == BODY PAYLOAD, WITH ONE CAVEAT. The frozen
  catalogue param (base64, tools/ble/catalogues/effect-library-H617A.json) is normally
  exactly the payload that follows this grammar's 3-byte prefix:
    body = 01 <linecount> <scene_type> || catalogue param || zero padding
  Applying Christmas 2189 and Bloom 2228 unedited each uploaded a payload byte-identical to
  its param, and the editors' Reset returned them to byte-identical. CAVEAT: a param can be
  STALE at an option-list offset. Glacier 2175 stores 0xff where both moveIn lists say the
  default is 250, and Mysterious 2214 stores 0xff where its brightValue list says 250. The
  app's live Glacier writes prove it overwrites stale param bytes from the option list on
  apply, so the option list is authoritative for every mapped field. An earlier Forest
  sample differed for an unrelated reason: that capture was of an Effects-Lab-EDITED
  Forest, not stock.

  RECORDS ARE NOT CATALOGUE PAGE ARRAY POSITIONS. Each catalogue config entry carries an
  explicit "page" number, and THAT is the record index; the entry's position in the config
  array is not. Using the array position resolves only 89 of the 99 adjustable-scene move
  controls, while using int(config[i]["page"]) resolves 97, and the remaining 2 are Glacier's
  stale moveIn bytes described above, whose live writes land exactly where the model says. So
  the model accounts for all 99 movement controls. Mysterious adds one stale
  brightness_speed byte that was invisible while the runtime ignored brightValue lists.

  ONE CATALOGUE ENTRY REMAINS UNRESOLVED. Heartbeat 2219 carries config pages
  1 and 2 for a body with only two records, and those entries contain only color and bright
  option lists. Every capture-backed config uses zero-based pages, so treating this one as
  one-based would be a scene-specific exception inferred from catalogue shape alone. The
  runtime leaves Heartbeat's Speed control unsupported until a live apply shows which record
  each entry changes.

  USER-AUTHORED SCENES SHIP THROUGH THIS SAME GRAMMAR UNDER ONE FIXED CODE.
  The app's "My DIY" list mixes two unrelated mechanisms.
  Entries with a pen/"DIY" badge are Flat/Combo DIYs (A3 TYPE 0x04, activated with
  33 05 0a <slot>, see govee_common::diy_selector and diy_type04.ksy). Entries with a
  rainbow-palette badge are custom Effects Lab SCENES: they upload an ordinary A3
  TYPE 0x02 body that follows this grammar exactly, then activate with
  33 05 04 92 01 — scene code 402 (0x0192). All four custom scenes on the test account
  shared that one code while carrying completely different bodies, and the connect-time
  read-back reports it as aa 05 04 92 01, so 402 is a fixed "whatever custom scene was
  last uploaded" code and not a catalogue id. It does not appear in the frozen
  catalogue, and integrations that map a scene code back to a name must expect it.

  402 IS NOT THE ONLY CODE OUTSIDE THE CATALOGUE. The app's
  "Light Up Your Life" surface activated codes 10314 and 10315, and neither is in the
  frozen H617A snapshot. That is NOT snapshot staleness, which was the obvious reading
  and was tested and rejected: re-querying the SKU endpoint on  returned
  H617A unchanged at 80 scenes / 83 effects and H6199 unchanged at 149 / 240, so the
  snapshot is current and complete FOR ITS SOURCE. The frozen file holds 83 codes
  spanning 0..16160, of which only 10005, 10006 and 10565 fall in the 10000 band, so
  10314 and 10315 sit inside the band and outside the set. The conclusion is about
  provenance rather than freshness: activatable scene codes exist that the per-SKU
  endpoint does not serve, so a name lookup keyed on that endpoint must fail soft for
  any code, not merely for 402. Where the app sources them is unestablished.

  AI IMAGE EFFECT IS A THIRD PRODUCER OF CODE 402. The AI
  section holds exactly one entry, "Image Effect: Upload pictures to generate lighting
  effects". Uploading a photograph produced an ordinary body under this grammar:
  187 bytes, linecount 11 (11 x 17 = 187 exactly), record_count 4, four records of
  rec_len 44, 184 bytes consumed with 3 zero padding bytes. It then activated with
  33 05 04 92 01 00, the same code as a hand-authored Effects Lab scene. So the cloud
  does the image analysis and hands back a scene definition; nothing device-facing is
  new, and the AI section needs no modelling of its own.

  These bodies are a useful corpus precisely because they are user-authored rather than
  vendor-frozen: they exercise record counts 1, 2 and 5, colour counts 1 and 2, and
  applied-area tiling, and every one parsed with zero excess. A five-record Christmas
  scene decoded as areas 20/22/24/26/28 carrying alternating red and green, matching
  what the strip actually shows.
seq:
  - id: header
    type: govee_common::a3_header
    doc: 'shared A3 body header 01 <linecount>; scene bodies span whole 17-byte chunks (Aurora linecount == len/17)'
  - id: scene_type
    type: u1
    enum: scene_type
    valid:
      eq: scene_type::scene_v2
    doc: 'catalogue scene_type selector (frame offset 2); values 0/1/2 exist and select DISTINCT body grammars (Sunrise=0, Halloween=1 code 0x0495, Aurora=2 code 0x0874), matching the frozen catalogue scene_type field. Only type 2 (rgbicv2) is modelled here; a type-1 body does not follow this record framing (proven: the Halloween body misparses, record_count reads 0x83) and is modelled by scene_type1_body.ksy, while type 0 has no body at all (those nine scenes ship an empty param, so nothing is uploaded). The valid guard fails the grammar closed on non-type-2 bodies. NAMING: this is the A3 BODY type byte, the same positional byte that workshop_body.ksy names a3_type; it is NOT the activation frame scene-type byte in command_write.ksy, which is a different byte and independent of this one.'
  - id: record_count
    type: u1
    doc: 'number of length-prefixed records that follow'
  - id: records
    type: record
    repeat: expr
    repeat-expr: record_count
    doc: 'record_count length-prefixed records'
  - id: padding
    type: u1
    valid: 0
    repeat: eos
    doc: 'transport zero padding to the A3 chunk boundary; grammar-enforced all-zero'
enums:
  scene_type:
    0: scene_v0
    1: scene_v1
    2: scene_v2
types:
  record:
    seq:
      - id: rec_len
        type: u1
        doc: 'number of record bytes that follow this length byte'
      - id: body
        type: govee_common::effect_layer
        size: rec_len
        doc: 'rec_len bytes of record body'
