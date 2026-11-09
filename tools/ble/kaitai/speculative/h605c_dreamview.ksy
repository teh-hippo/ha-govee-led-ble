meta:
  id: h605c_dreamview
  title: H605C revision-selected local DreamView frames
  imports:
    - h6199_dreamview_frame
    - h6099_dreamview_frame
doc: |
  SPECULATIVE exact-model revision contract. Pact 1/1 uses legacy independent
  command opcodes and a five-member fallback capacity. Pact 1/2 selects module
  60 and the seven-member fallback capacity. These are product fallbacks;
  anonymous status slots do not establish group membership or capacity.
  Both revisions support group switch, member brightness and connection,
  same brightness, saturation, video settings, sound and deletion. The
  legacy revision uses the module-60 same-brightness command alongside its
  otherwise independent opcodes. Do not copy the other product's firmware
  gate for that operation.
  Group roster uploads use shared A3 type 50 member records; legacy
  completion is checked before locally authored membership changes.
  Acceptance does not establish visible synchronisation. Cloud roster
  management and camera calibration are not part of this local contract.
  The selected shared codecs preserve uncertain reply suffixes.
params:
  - id: modern
    type: bool
  - id: is_query
    type: bool
seq:
  - id: legacy
    type: h6199_dreamview_frame(is_query)
    if: not modern
  - id: current
    type: h6099_dreamview_frame(is_query)
    if: modern
