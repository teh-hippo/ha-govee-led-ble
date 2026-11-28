"""Profile-selected native-effect format and carrier policies."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Any

from kaitaistruct import KaitaiStructError

from .const import ModelProfile, get_profile
from .h1ab2_effects import (
    decode_accumulation,
    encode_accumulation,
    validate_h1ab2_structure,
)
from .h60a6_effects import (
    decode_native_body,
    encode_native_body,
    validate_h60a6_structure,
)
from .h60b0_diy import encode_h60b0_diy, validate_h60b0_structure
from .h60b2_effects import encode_h60b2_diy, validate_h60b2_structure
from .h607c_effects import (
    decode_zoned_diy,
    encode_h607c_layered_scene,
    encode_zoned_diy,
    validate_h607c_layered_payload,
    validate_h607c_structure,
)
from .h1771_effects import (
    decode_h1771_diy,
    decode_h1771_scene,
    encode_h1771_diy,
    encode_h1771_scene,
    validate_h1771_structure,
)
from .h7025_effects import decode_h7025_diy, encode_h7025_diy, validate_h7025_diy
from .layered_scene import LayeredScene
from .native_effect import NativeEffect
from .projector_protocol import decode_projector, encode_projector, validate_projector_structure
from .protocol_core import (
    DiyType03,
    DiyType04,
    H1ab2DiyBody,
    H1ab2PaintBody,
    H60a6DiyBody,
    H60a6EffectFrame,
    H60a6PaintBody,
    H60b0CommandAck,
    H60b2DiyBody,
    H60b2EffectUpload,
    H607cDiyBody,
    H607cEffectUpload,
    H607cPaintBody,
    H607cSceneBody,
    H1771DiyBody,
    H1771EffectUpload,
    H6022EffectUpload,
    H6022SceneBody,
    H6093Projector,
    H7025DiyBody,
    SceneBody,
    SceneType1Body,
)
from .protocol_imports import load_generated_class
from .scenes import SceneEntry

H60b0EffectUpload = load_generated_class("h60b0_effect_upload", "H60b0EffectUpload")
H60b0SceneBody = load_generated_class("h60b0_scene_body", "H60b0SceneBody")


class NativeEffectCarrier(StrEnum):
    A3 = "a3"
    A4 = "a4"


class NativeUploadPurpose(StrEnum):
    CUSTOM = "custom"
    SCENE = "scene"
    APPEARANCE = "appearance"
    MUSIC = "music"
    LAYERED_SCENE = "layered_scene"
    PAINT = "paint"
    OTHER_SCENE = "other_scene"


@dataclass(frozen=True, slots=True)
class NativeUploadRoute:
    carrier: NativeEffectCarrier
    subtype: int
    purpose: NativeUploadPurpose
    root_type: type[Any] | None = None
    families: frozenset[int] = frozenset()
    fixed_selector: int | None = None
    scene_activation: bool = False
    requires_zero_padding: bool = False

    def matches(self, family: int, *, scene: bool) -> bool:
        if self.families and family not in self.families:
            return False
        return self.purpose is NativeUploadPurpose.SCENE if scene else self.purpose is NativeUploadPurpose.CUSTOM


StructureValidator = Callable[[NativeEffect], None]
AuthoredValidator = Callable[[NativeEffect, str, ModelProfile, Any], None]
EncodeContent = Callable[[NativeEffect], bytes]
DecodePayload = Callable[[bytes, int], NativeEffect]
DecodeTree = Callable[[Any], NativeEffect]
DecodeScene = Callable[[Any, bytes, int], NativeEffect]
PrepareBody = Callable[[bytes, NativeEffect, bool], bytes]
SceneRoute = Callable[[SceneEntry], NativeUploadRoute | None]
Workflow = Callable[[NativeEffect], str]


@dataclass(frozen=True, slots=True)
class NativeEffectCodec:
    codec_id: str
    effect_grammar: str
    canonical_target: str
    validate_structure: StructureValidator
    encode: EncodeContent
    decode: DecodePayload
    validate_authored: AuthoredValidator | None = None
    workflow: Workflow | None = None
    routes: tuple[NativeUploadRoute, ...] = ()
    scene_route: SceneRoute | None = None
    decode_tree: DecodeTree | None = None
    decode_scene: DecodeScene | None = None
    parse_scene_body: Callable[[bytes, int], Any] | None = None
    prepare_body: PrepareBody | None = None
    prepare_scene_payload: Callable[[bytes, int, Any], bytes] | None = None
    prepare_layered_payload: Callable[[bytes], bytes] | None = None
    validate_tree: Callable[[Any, ModelProfile], None] | None = None
    serialised_fields: frozenset[str] = frozenset()
    catalogue_scene_families: frozenset[int] = frozenset()
    opaque_scene_families: frozenset[int] = frozenset()
    selector_only_native_scene: bool = False
    combined_layered_scenes: bool = False
    combined_music_zones: tuple[tuple[str, ...], ...] = ()
    allows_zone_style: bool = False
    preserves_unspecified_scene_speed: bool = False
    native_catalogue: bool = False
    template_available: Callable[[NativeEffect, ModelProfile], bool] | None = None
    decode_layered: Callable[[Any, bytes, int | None], LayeredScene] | None = None
    encode_layered: Callable[[LayeredScene], bytes] | None = None
    apply_layered_speed: Callable[[bytes, Any, int], bytes] | None = None
    scene_speed_type: int | None = None
    validate_layered_payload: Callable[[bytes], None] | None = None
    reports_body_effect_code: bool = False
    physical_geometry_family: int | None = None
    layered_scene_type: int | None = None
    paint_selector: int | None = None
    a4_frame_type: type[Any] | None = None
    native_tree_types: tuple[type[Any], ...] = ()
    admit_upload: Callable[[ModelProfile, int], bool | None] | None = None
    native_only_diy: bool = False
    profile_subtype_qualified: bool = False
    explicit_profile_required: bool = False

    @property
    def canonical_model(self) -> str:
        return self.canonical_target

    @property
    def carrier(self) -> NativeEffectCarrier:
        return self.routes[0].carrier if self.routes else NativeEffectCarrier.A3

    @property
    def upload_subtype(self) -> int:
        if not self.routes:
            raise ValueError(f"{self.codec_id} has no upload route")
        return self.routes[0].subtype

    @property
    def root_type(self) -> type[Any]:
        root_type = self.routes[0].root_type if self.routes else None
        if root_type is None:
            raise ValueError(f"{self.codec_id} has no generated A3 root")
        return root_type

    def workflow_for(self, content: NativeEffect) -> str:
        if content.template is not None:
            return "layered_scenes"
        if self.workflow is None:
            return "single"
        return self.workflow(content)

    def route_for_content(self, content: NativeEffect, *, scene: bool = False) -> NativeUploadRoute:
        for route in self.routes:
            if route.matches(content.family, scene=scene):
                return route
        raise ValueError(f"{self.canonical_target} has no qualified native effect upload route")

    def scene_route_for(self, scene: SceneEntry) -> NativeUploadRoute | None:
        if self.scene_route is not None:
            return self.scene_route(scene)
        if scene.scene_type != 5:
            return next(
                (
                    route
                    for route in self.routes
                    if route.purpose in {NativeUploadPurpose.LAYERED_SCENE, NativeUploadPurpose.OTHER_SCENE}
                    and (route.subtype == scene.scene_type or self.layered_scene_type == scene.scene_type)
                ),
                None,
            )
        if scene.scene_type != 5 or len(scene.diy_effect_codes) != 1:
            return None
        family = scene.diy_effect_codes[0]
        return next(
            (route for route in self.routes if route.purpose is NativeUploadPurpose.SCENE and family in route.families),
            None,
        )

    def a3_root_for_subtype(self, subtype: int) -> type[Any] | None:
        return next(
            (
                route.root_type
                for route in self.routes
                if route.carrier is NativeEffectCarrier.A3 and route.subtype == subtype and route.root_type is not None
            ),
            None,
        )

    def admits_upload(self, profile: ModelProfile, subtype: int) -> bool | None:
        if not profile.command_operation_supported("effect_upload"):
            return False
        explicit = self.admit_upload(profile, subtype) if self.admit_upload is not None else None
        if explicit is not None:
            return explicit
        routes = [route for route in self.routes if route.subtype == subtype]
        if not routes:
            return False
        if (
            self.profile_subtype_qualified
            and subtype == self.upload_subtype
            and profile.native_diy_upload_subtype != subtype
        ):
            return False
        return any(
            (
                route.purpose is NativeUploadPurpose.CUSTOM
                and profile.supports_custom_effects
                or route.purpose
                in {
                    NativeUploadPurpose.SCENE,
                    NativeUploadPurpose.LAYERED_SCENE,
                    NativeUploadPurpose.OTHER_SCENE,
                }
                and profile.supports_scenes
                or route.purpose is NativeUploadPurpose.APPEARANCE
                and profile.projector_control_revision is not None
                or route.purpose is NativeUploadPurpose.MUSIC
                and profile.command_operation_supported("music")
                or route.purpose is NativeUploadPurpose.PAINT
                and profile.supports_custom_effects
            )
            for route in routes
        )

    def requires_zero_padding_for(self, subtype: int, root_type: type[Any]) -> bool:
        return any(
            route.subtype == subtype and route.root_type is root_type and route.requires_zero_padding
            for route in self.routes
        )

    def qualifies_upload_subtype(self, profile: ModelProfile, subtype: int) -> bool:
        return (
            not self.profile_subtype_qualified
            or subtype != self.upload_subtype
            or profile.native_diy_upload_subtype == subtype
        )

    def parse_scene(self, payload: bytes, family: int) -> Any:
        if self.parse_scene_body is None:
            raise ValueError("Native scene has no documented body family")
        return self.parse_scene_body(payload, family)

    def content_available_for_profile(self, content: NativeEffect, profile: ModelProfile) -> bool:
        return self.template_available is None or self.template_available(content, profile)

    def decode_scene_content(self, scene_ref: Any, payload: bytes, family: int) -> NativeEffect:
        if self.decode_scene is None:
            from dataclasses import replace

            return replace(self.decode(payload, family), template=scene_ref)
        return self.decode_scene(scene_ref, payload, family)

    def prepare_upload(self, body: bytes, content: NativeEffect, *, scene: bool) -> bytes:
        return body if self.prepare_body is None else self.prepare_body(body, content, scene)

    def decode_parsed(self, tree: Any) -> NativeEffect:
        if self.decode_tree is None:
            raise ValueError("Native upload requires source topology or catalogue identity")
        return self.decode_tree(tree)

    def family_for_carrier(self, carrier: NativeEffectCarrier, subtype: int) -> int:
        families = {
            family
            for route in self.routes
            if route.carrier is carrier and route.subtype == subtype
            for family in route.families
        }
        if len(families) != 1:
            raise ValueError("Native upload route does not identify one body family")
        return families.pop()


def _h60a6_route(content_family: int) -> NativeUploadRoute:
    return NativeUploadRoute(
        NativeEffectCarrier.A4 if content_family == 798 else NativeEffectCarrier.A3,
        int(H60a6EffectFrame.Subtype.native_effect),
        NativeUploadPurpose.CUSTOM,
        H60a6EffectFrame.A3Envelope if content_family == 797 else None,
        frozenset({content_family}),
        requires_zero_padding=True,
    )


def _decode_h60a6_tree(tree: Any) -> NativeEffect:
    if isinstance(tree, H60a6DiyBody):
        from .protocol_core import serialize_native_body

        return decode_native_body(serialize_native_body(tree), family=797)
    if isinstance(getattr(tree, "body", None), H60a6DiyBody):
        from .protocol_core import serialize_native_body

        return decode_native_body(serialize_native_body(tree.body), family=797)
    payload = getattr(tree, "payload", None)
    if isinstance(payload, bytes):
        return decode_native_body(payload, family=797)
    raise TypeError("tree is not a generated native DIY body")


def _decode_h1771_tree(tree: Any) -> NativeEffect:
    from .protocol_core import serialize_native_body

    if not isinstance(tree, H1771EffectUpload) or tree.kind != H1771EffectUpload.UploadKind.native_diy:
        raise ValueError("Native scene upload requires catalogue identity")
    if tree.body.unknown_tail:
        raise ValueError("Native upload cannot distinguish extensions from transport fill")
    return decode_h1771_diy(serialize_native_body(tree.body))


def _decode_h607c_tree(tree: Any) -> NativeEffect:
    from .protocol_core import serialize_native_body

    if tree.kind != H607cEffectUpload.Kind.native_diy:
        raise ValueError("Native upload requires source topology or catalogue identity")
    return decode_zoned_diy(serialize_native_body(tree.content))


def _decode_h1ab2_tree(tree: Any) -> NativeEffect:
    from .protocol_core import serialize_native_body

    if not isinstance(tree, H1ab2DiyBody.Upload):
        raise TypeError("tree is not a generated native Accumulation upload")
    if any(tree.padding):
        raise ValueError("Native upload has unrepresented trailing data")
    return decode_accumulation(serialize_native_body(tree.body))


def _decode_h6093_tree(tree: Any) -> NativeEffect:
    from .protocol_core import serialize_native_body

    if tree.kind != H6093Projector.UploadKind.diy:
        raise ValueError("Projector scene upload requires catalogue identity")
    return decode_projector(b"\x48" + serialize_native_body(tree.body))


def _decode_h7025_tree(tree: Any) -> NativeEffect:
    from .protocol_core import serialize_native_body

    return decode_h7025_diy(serialize_native_body(tree.body))


def _parse_h60a6_scene(payload: bytes, family: int) -> Any:
    root_type = H60a6DiyBody if family == 797 else H60a6PaintBody if family == 798 else None
    if root_type is None:
        raise ValueError("Native scene has no documented body family")
    root = root_type.from_bytes(payload)
    root._read()
    if not root._io.is_eof():
        raise ValueError("Native scene body contains trailing data")
    return root


def _apply_h60a6_scene_speed(payload: bytes, speed: Any, index: int) -> bytes:
    from .protocol_core import serialize_native_body

    if not 0 <= index < speed.option_count:
        raise ValueError("Scene speed index is outside its documented options")
    root = _parse_h60a6_scene(payload, 797)
    speed.validate_layer_count(root.payload.layer_count)
    for layer, value in zip(root.payload.layers, speed.layer_speeds[index], strict=True):
        if not hasattr(layer.body, "speed"):
            raise ValueError("Scene speed targets an unknown native layer")
        layer.body.speed = value
    return serialize_native_body(root)


def _validate_h60a6_layered_payload(payload: bytes) -> None:
    try:
        _parse_h60a6_scene(payload, 797)
    except (EOFError, ValueError, KaitaiStructError) as error:
        raise ValueError("Invalid native H60A6 scene body") from error


def _prepare_h1771_scene_payload(payload: bytes, family: int, parsed: Any) -> bytes:
    from .protocol_core import serialize_native_body

    return serialize_native_body(parsed.body)


def _prepare_h6093_scene_payload(payload: bytes, family: int, parsed: Any) -> bytes:
    return payload[len(parsed.marker) :]


def _prepare_h60b0_layered_payload(payload: bytes) -> bytes:
    from .h60b0_effects import combined_upload_body

    return combined_upload_body(payload)


def _parse_h6093_scene(payload: bytes, family: int) -> Any:
    decode_projector(payload)
    root = H6093Projector.from_bytes(payload)
    root._read()
    return root


def _parse_h1771_scene(payload: bytes, family: int) -> Any:
    import io

    from kaitaistruct import KaitaiStream

    root = H1771DiyBody.Scene(KaitaiStream(io.BytesIO(payload)), _root=H1771DiyBody())
    root._read()
    if not root._io.is_eof():
        raise ValueError("Native scene body contains trailing data")
    return root


def _parse_h6022_scene(payload: bytes, family: int) -> Any:
    professional = family == 693
    root = H6022SceneBody.from_bytes(payload)
    root._read()
    if root.marker != (0x41 if professional else 0):
        raise ValueError("H6022 native scene marker does not match its body family")
    return root


def _validate_h6093_tree(tree: Any, profile: ModelProfile) -> None:
    import io

    from kaitaistruct import KaitaiStream

    if tree.kind not in (
        H6093Projector.UploadKind.scene,
        H6093Projector.UploadKind.diy,
        H6093Projector.UploadKind.appearance,
    ):
        raise ValueError("Unknown projector upload command")
    if tree.kind == H6093Projector.UploadKind.appearance:
        from .projector_protocol import decode_appearance

        if profile.projector_control_revision is None:
            raise ValueError("Projector appearance requires its qualified revision")
        appearance = H6093Projector.Appearance(
            profile.projector_control_revision == 1,
            KaitaiStream(io.BytesIO(tree.body)),
        )
        appearance._read()
        decode_appearance(appearance)


def _validate_h60b0_tree(tree: Any, profile: ModelProfile) -> None:
    if getattr(tree.kind, "name", None) is None:
        raise ValueError("Unknown native upload command")


def _validate_h607c_tree(tree: Any, profile: ModelProfile) -> None:
    if getattr(tree.kind, "name", None) is None:
        raise ValueError("Unknown native upload command")
    if tree.kind == H607cEffectUpload.Kind.layered_scene:
        from .protocol_core import H607cSceneBody

        for record in tree.content.records:
            trailer = H607cSceneBody.LayerTrailer.from_bytes(record.body.excess)
            trailer._read()


def _admit_h607c_upload(profile: ModelProfile, subtype: int) -> bool | None:
    kinds = H607cEffectUpload.Kind
    admitted = {
        int(kinds.dreamview_palette): "music" in profile.dreamview_operations,
        int(kinds.dreamview_protocols): "music" in profile.dreamview_operations,
        int(kinds.dreamview_scene): "scene" in profile.dreamview_operations,
        int(kinds.dreamview_group): "replace_group" in profile.dreamview_operations,
    }
    return admitted.get(subtype)


def _prepare_h1771_body(body: bytes, content: NativeEffect, scene: bool) -> bytes:
    from .native_scenes import _parse_native_scene_body
    from .protocol_core import serialize_native_body

    if not scene or content.template is None:
        return body
    return serialize_native_body(_parse_native_scene_body(body, content.family).body)


def _prepare_h6093_body(body: bytes, content: NativeEffect, scene: bool) -> bytes:
    from .native_scenes import _parse_native_scene_body

    parsed = _parse_native_scene_body(body, content.family)
    return body[len(parsed.marker) :]


def _h60b0_scene_route(scene: SceneEntry) -> NativeUploadRoute | None:
    if scene.scene_type != 6:
        return None
    return NativeUploadRoute(
        NativeEffectCarrier.A3,
        int(H60b0SceneBody.UploadSubtype.combined),
        NativeUploadPurpose.LAYERED_SCENE,
        H60b0EffectUpload,
    )


def _decode_h60b0_layered(template: Any, payload: bytes, speed_index: int | None) -> LayeredScene:
    from .h60b0_effects import decode_combined_scene

    return decode_combined_scene(template, payload, speed_index=speed_index)


def _encode_h60b0_layered(scene: LayeredScene) -> bytes:
    from .h60b0_effects import encode_combined_scene

    return encode_combined_scene(scene)


def _apply_h60b0_layered_speed(payload: bytes, speed: Any, index: int) -> bytes:
    from .h60b0_effects import apply_combined_speed

    return apply_combined_speed(payload, speed, index)


def _validate_h60b0_layered_payload(payload: bytes) -> None:
    from .h60b0_effects import parse_combined_scene

    parse_combined_scene(payload)


def _h6022_scene_route(scene: SceneEntry) -> NativeUploadRoute | None:
    if scene.scene_type != 5 or len(scene.diy_effect_codes) != 1:
        return None
    return NativeUploadRoute(
        NativeEffectCarrier.A3,
        0x58 if scene.diy_effect_codes[0] == 693 else 0x04,
        NativeUploadPurpose.SCENE,
        H6022EffectUpload,
        frozenset(scene.diy_effect_codes),
    )


def _catalogue_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    from .effect_catalogue import _validate_native_zone_eligibility

    _validate_native_zone_eligibility(content, target, profile, catalogue)


def _h60a6_author_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    from .native_effect import NativeDiyLayer

    if content.model != target or not profile.supports_custom_effects:
        raise ValueError("native content does not match the target profile")
    if content.family == 798 and profile.physical_ic_count != 133:
        raise ValueError("native paint requires the exact 133-point geometry")
    if any(isinstance(layer, NativeDiyLayer) and not 1 <= len(layer.palette) <= 8 for layer in content.layers):
        raise ValueError("native DIY palette must contain 1 to 8 colours")


def _h1771_author_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    from .effect_catalogue_templates import _H1771_SECTIONS, _h1771_rate_min
    from .native_effect import NativeDiyLayer, NativeOpaqueLayer

    if content.model != target:
        raise ValueError("native content target does not match the selected codec")
    if not any(isinstance(layer, NativeDiyLayer) and layer.enabled for layer in content.layers):
        raise ValueError("select at least one native effect section")
    for index, layer in enumerate(content.layers):
        if isinstance(layer, NativeOpaqueLayer):
            if content.template is None:
                raise ValueError("unqualified native section cannot be authored")
            continue
        if not isinstance(layer, NativeDiyLayer):
            raise ValueError("unsupported native effect section")
        if not layer.enabled:
            continue
        matches = [seed for _label, seed in _H1771_SECTIONS[index] if seed.kind == layer.kind]
        if not matches:
            raise ValueError("native effect is not available in this section")
        temperature = not matches[0].palette
        if temperature:
            if not 1000 <= layer.angle <= 10000 or not 0 <= layer.parameter <= 100:
                raise ValueError("native colour temperature or brightness is outside the supported range")
        elif not 1 <= len(layer.palette) <= 8 or not any(
            (layer.parameter, layer.flag) == (seed.parameter, seed.flag) for seed in matches
        ):
            if content.template is None:
                raise ValueError("native effect palette or variation is unsupported")
        if layer.speed < _h1771_rate_min(index, layer.kind) and content.template is None:
            raise ValueError("native effect speed must be at least one")


def _projector_author_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    validate_projector_structure(content)
    if content.model != target or not any(
        layer.coarse.enabled or layer.fine is not None and layer.fine.enabled or layer.stars.enabled
        for layer in content.projector_layers
    ):
        raise ValueError("Select at least one projector light source")


def _h60b0_author_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    from .h60b0_diy import validate_h60b0_diy

    validate_h60b0_diy(content, profile.native_effect_revision)


def _h7025_author_validator(content: NativeEffect, target: str, profile: ModelProfile, catalogue: Any) -> None:
    validate_h7025_diy(content)


def _reject_opaque_decode(tree: Any) -> NativeEffect:
    raise ValueError("H6022 effect bodies require authored content or catalogue identity")


H6022_SCENE_FAMILIES = frozenset({1, 18, 33, 389, 390, 464, 693})
H6022_PROFESSIONAL_SCENE_FAMILIES = frozenset({693})

H60A6_SCENE_FAMILIES = frozenset({797, 798})
H60B0_NATIVE_FAMILIES = frozenset({*range(1, 14), 81, 922, 923})
H1771_FAMILY = int(H1771DiyBody.CatalogueFamily.native_scene)
H6093_FAMILY = int(H6093Projector.CatalogueFamily.projector)


NATIVE_EFFECT_CODECS: tuple[NativeEffectCodec, ...] = (
    NativeEffectCodec(
        codec_id="h7025-a3-0x58",
        effect_grammar="H617A",
        canonical_target="H7025",
        validate_structure=validate_h7025_diy,
        encode=encode_h7025_diy,
        decode=lambda payload, family: decode_h7025_diy(payload),
        validate_authored=_h7025_author_validator,
        workflow=lambda content: "single",
        decode_tree=_decode_h7025_tree,
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                0x58,
                NativeUploadPurpose.CUSTOM,
                H7025DiyBody,
                frozenset({767}),
                requires_zero_padding=True,
            ),
            NativeUploadRoute(NativeEffectCarrier.A3, 1, NativeUploadPurpose.OTHER_SCENE, SceneType1Body),
            NativeUploadRoute(NativeEffectCarrier.A3, 2, NativeUploadPurpose.LAYERED_SCENE, SceneBody),
            NativeUploadRoute(NativeEffectCarrier.A3, 3, NativeUploadPurpose.PAINT, DiyType03),
            NativeUploadRoute(NativeEffectCarrier.A3, 4, NativeUploadPurpose.CUSTOM, DiyType04),
        ),
        serialised_fields=frozenset({"enabled"}),
        profile_subtype_qualified=True,
        explicit_profile_required=True,
    ),
    NativeEffectCodec(
        codec_id="h60a6",
        effect_grammar="H60A6",
        canonical_target="H60A6",
        validate_structure=validate_h60a6_structure,
        encode=encode_native_body,
        decode=lambda payload, family: decode_native_body(payload, family=family),
        validate_authored=_h60a6_author_validator,
        workflow=lambda content: (
            "painted" if content.family == 798 else "advanced" if content.preset_id in (11, 12) else "single"
        ),
        routes=(
            _h60a6_route(797),
            NativeUploadRoute(
                NativeEffectCarrier.A4,
                int(H60a6EffectFrame.Subtype.native_effect),
                NativeUploadPurpose.CUSTOM,
                None,
                frozenset({798}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60a6EffectFrame.Subtype.native_effect),
                NativeUploadPurpose.SCENE,
                H60a6EffectFrame.A3Envelope,
                frozenset({797}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A4,
                int(H60a6EffectFrame.Subtype.native_effect),
                NativeUploadPurpose.SCENE,
                None,
                frozenset({798}),
            ),
        ),
        decode_tree=_decode_h60a6_tree,
        parse_scene_body=_parse_h60a6_scene,
        catalogue_scene_families=H60A6_SCENE_FAMILIES,
        native_tree_types=(H60a6DiyBody,),
        validate_tree=lambda tree, profile: None,
        native_catalogue=True,
        physical_geometry_family=798,
        a4_frame_type=H60a6EffectFrame,
        scene_speed_type=5,
        validate_layered_payload=_validate_h60a6_layered_payload,
        apply_layered_speed=lambda payload, speed, index: _apply_h60a6_scene_speed(payload, speed, index),
    ),
    NativeEffectCodec(
        codec_id="h6093-projector",
        effect_grammar="H6093",
        canonical_target="H6093",
        validate_structure=validate_projector_structure,
        encode=encode_projector,
        decode=lambda payload, family: decode_projector(payload),
        validate_authored=_projector_author_validator,
        workflow=lambda content: "advanced" if content.preset_id is None else "single",
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H6093Projector.UploadKind.diy),
                NativeUploadPurpose.CUSTOM,
                H6093Projector.Upload,
                frozenset({H6093_FAMILY}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H6093Projector.UploadKind.scene),
                NativeUploadPurpose.SCENE,
                H6093Projector.Upload,
                frozenset({H6093_FAMILY}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H6093Projector.UploadKind.appearance),
                NativeUploadPurpose.APPEARANCE,
                H6093Projector.Upload,
            ),
        ),
        decode_tree=_decode_h6093_tree,
        parse_scene_body=_parse_h6093_scene,
        prepare_body=_prepare_h6093_body,
        prepare_scene_payload=_prepare_h6093_scene_payload,
        validate_tree=_validate_h6093_tree,
        catalogue_scene_families=frozenset({H6093_FAMILY}),
        serialised_fields=frozenset({"projector_layers"}),
    ),
    NativeEffectCodec(
        codec_id="h60b0",
        effect_grammar="H60B0",
        canonical_target="H60B0",
        validate_structure=validate_h60b0_structure,
        encode=encode_h60b0_diy,
        decode=lambda payload, family: (_ for _ in ()).throw(
            ValueError("Native uploads require their qualified revision and retained source definition")
        ),
        validate_authored=_h60b0_author_validator,
        workflow=lambda content: (
            "advanced"
            if content.family in (13, 923)
            else "multi"
            if content.family == 81 or content.revision == 3
            else "single"
        ),
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60b0SceneBody.UploadSubtype.combined),
                NativeUploadPurpose.CUSTOM,
                H60b0EffectUpload,
                frozenset({81}),
                fixed_selector=int(H60b0SceneBody.ActivationSelector.temporary),
                scene_activation=True,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60b0CommandAck.UploadKind.native_diy),
                NativeUploadPurpose.CUSTOM,
                H60b0EffectUpload,
                H60B0_NATIVE_FAMILIES - {81},
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60b0SceneBody.UploadSubtype.combined),
                NativeUploadPurpose.LAYERED_SCENE,
                H60b0EffectUpload,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60b0SceneBody.UploadSubtype.rgbic_scene),
                NativeUploadPurpose.LAYERED_SCENE,
                H60b0EffectUpload,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                0x41,
                NativeUploadPurpose.MUSIC,
                H60b0EffectUpload,
            ),
        ),
        scene_route=_h60b0_scene_route,
        serialised_fields=frozenset({"enabled", "secondary_palette", "temperatures", "section_tail", "revision"}),
        combined_layered_scenes=True,
        decode_layered=_decode_h60b0_layered,
        encode_layered=_encode_h60b0_layered,
        apply_layered_speed=_apply_h60b0_layered_speed,
        scene_speed_type=6,
        validate_layered_payload=_validate_h60b0_layered_payload,
        prepare_layered_payload=_prepare_h60b0_layered_payload,
        combined_music_zones=(("side", "ripple"),),
        allows_zone_style=True,
        preserves_unspecified_scene_speed=True,
        reports_body_effect_code=True,
        layered_scene_type=6,
        template_available=lambda content, profile: (
            content.family == 81
            or (
                profile.native_effect_revision in (1, 2)
                if content.revision == 1
                else profile.native_effect_revision == 3
            )
        ),
        validate_tree=_validate_h60b0_tree,
    ),
    NativeEffectCodec(
        codec_id="h1771",
        effect_grammar="H1771",
        canonical_target="H1771",
        validate_structure=validate_h1771_structure,
        encode=lambda content: (
            encode_h1771_scene(content) if content.template is not None else encode_h1771_diy(content)
        ),
        decode=lambda payload, family: decode_h1771_diy(payload),
        validate_authored=_h1771_author_validator,
        workflow=lambda content: "multi",
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1771EffectUpload.UploadKind.native_diy),
                NativeUploadPurpose.CUSTOM,
                H1771EffectUpload,
                frozenset({H1771_FAMILY}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1771EffectUpload.UploadKind.native_diy),
                NativeUploadPurpose.SCENE,
                H1771EffectUpload,
                frozenset({H1771_FAMILY}),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1771EffectUpload.UploadKind.rgb_scene),
                NativeUploadPurpose.OTHER_SCENE,
                SceneType1Body,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1771EffectUpload.UploadKind.layered_scene),
                NativeUploadPurpose.LAYERED_SCENE,
                SceneBody,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1771EffectUpload.UploadKind.music),
                NativeUploadPurpose.MUSIC,
            ),
        ),
        decode_tree=_decode_h1771_tree,
        decode_scene=lambda scene_ref, payload, family: replace(decode_h1771_scene(payload), template=scene_ref),
        parse_scene_body=_parse_h1771_scene,
        prepare_body=_prepare_h1771_body,
        prepare_scene_payload=_prepare_h1771_scene_payload,
        catalogue_scene_families=frozenset({H1771_FAMILY}),
        selector_only_native_scene=True,
        serialised_fields=frozenset({"enabled", "secondary_palette", "section_tail"}),
    ),
    NativeEffectCodec(
        codec_id="h607c-zoned",
        effect_grammar="H607C",
        canonical_target="H607C",
        validate_structure=validate_h607c_structure,
        encode=encode_zoned_diy,
        decode=lambda payload, family: decode_zoned_diy(payload),
        validate_authored=_catalogue_validator,
        workflow=lambda content: "multi" if content.family == int(H607cDiyBody.Family.paired) else "single",
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H607cDiyBody.UploadSubtype.native_diy),
                NativeUploadPurpose.CUSTOM,
                H607cEffectUpload,
                frozenset(int(family) for family in H607cDiyBody.Family),
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H607cEffectUpload.Kind.layered_scene),
                NativeUploadPurpose.LAYERED_SCENE,
                H607cEffectUpload,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H607cEffectUpload.Kind.paint),
                NativeUploadPurpose.PAINT,
                H607cEffectUpload,
            ),
            *(
                NativeUploadRoute(
                    NativeEffectCarrier.A3,
                    int(kind),
                    NativeUploadPurpose.MUSIC
                    if kind == H607cEffectUpload.Kind.music
                    else NativeUploadPurpose.OTHER_SCENE,
                    H607cEffectUpload,
                )
                for kind in (
                    H607cEffectUpload.Kind.music,
                    H607cEffectUpload.Kind.dreamview_palette,
                    H607cEffectUpload.Kind.dreamview_protocols,
                    H607cEffectUpload.Kind.dreamview_scene,
                    H607cEffectUpload.Kind.dreamview_group,
                )
            ),
        ),
        decode_tree=_decode_h607c_tree,
        validate_tree=_validate_h607c_tree,
        admit_upload=_admit_h607c_upload,
        encode_layered=encode_h607c_layered_scene,
        serialised_fields=frozenset({"enabled", "secondary_palette"}),
        reports_body_effect_code=True,
        layered_scene_type=int(H607cSceneBody.CatalogueType.layered_scene),
        scene_speed_type=6,
        validate_layered_payload=validate_h607c_layered_payload,
        paint_selector=int(H607cPaintBody.ActivationSelector.static_paint),
        native_only_diy=True,
    ),
    NativeEffectCodec(
        codec_id="h1ab2-accumulation",
        effect_grammar="H1AB2",
        canonical_target="H1AB2",
        validate_structure=validate_h1ab2_structure,
        encode=encode_accumulation,
        decode=lambda payload, family: decode_accumulation(payload),
        validate_authored=_catalogue_validator,
        workflow=lambda content: "single",
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H1ab2DiyBody.UploadSubtype.native_diy),
                NativeUploadPurpose.CUSTOM,
                H1ab2DiyBody.Upload,
                frozenset({int(H1ab2DiyBody.CatalogueFamily.accumulation)}),
            ),
            NativeUploadRoute(NativeEffectCarrier.A3, 1, NativeUploadPurpose.OTHER_SCENE, SceneType1Body),
            NativeUploadRoute(NativeEffectCarrier.A3, 2, NativeUploadPurpose.LAYERED_SCENE, SceneBody),
            NativeUploadRoute(NativeEffectCarrier.A3, 3, NativeUploadPurpose.PAINT, H1ab2PaintBody),
            NativeUploadRoute(NativeEffectCarrier.A3, 4, NativeUploadPurpose.CUSTOM, DiyType04),
        ),
        decode_tree=_decode_h1ab2_tree,
    ),
    NativeEffectCodec(
        codec_id="h60b2-palette",
        effect_grammar="H60B2",
        canonical_target="H60B2",
        validate_structure=validate_h60b2_structure,
        encode=encode_h60b2_diy,
        decode=lambda payload, family: (_ for _ in ()).throw(
            ValueError("Native palette uploads require retained source definition")
        ),
        validate_authored=_catalogue_validator,
        workflow=lambda content: "single",
        routes=(
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                int(H60b2DiyBody.UploadSubtype.native_diy),
                NativeUploadPurpose.CUSTOM,
                H60b2EffectUpload,
                frozenset({803}),
            ),
            NativeUploadRoute(NativeEffectCarrier.A3, 1, NativeUploadPurpose.OTHER_SCENE, SceneType1Body),
            NativeUploadRoute(NativeEffectCarrier.A3, 2, NativeUploadPurpose.LAYERED_SCENE, SceneBody),
            NativeUploadRoute(NativeEffectCarrier.A3, 3, NativeUploadPurpose.PAINT, DiyType03),
            NativeUploadRoute(NativeEffectCarrier.A3, 4, NativeUploadPurpose.CUSTOM, DiyType04),
        ),
    ),
    NativeEffectCodec(
        codec_id="h6022-opaque-scenes",
        effect_grammar="H6022",
        canonical_target="H6022",
        validate_structure=lambda content: (_ for _ in ()).throw(
            ValueError("H6022 native scenes remain opaque catalogue content")
        ),
        encode=lambda content: (_ for _ in ()).throw(ValueError("H6022 native scenes require catalogue identity")),
        decode=lambda payload, family: (_ for _ in ()).throw(
            ValueError("H6022 effect bodies require authored content or catalogue identity")
        ),
        workflow=lambda content: "native_scenes",
        routes=(
            NativeUploadRoute(NativeEffectCarrier.A3, 1, NativeUploadPurpose.OTHER_SCENE, H6022EffectUpload),
            NativeUploadRoute(NativeEffectCarrier.A3, 2, NativeUploadPurpose.LAYERED_SCENE, H6022EffectUpload),
            NativeUploadRoute(NativeEffectCarrier.A3, 3, NativeUploadPurpose.PAINT, H6022EffectUpload),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                0x04,
                NativeUploadPurpose.SCENE,
                H6022EffectUpload,
                H6022_SCENE_FAMILIES - H6022_PROFESSIONAL_SCENE_FAMILIES,
            ),
            NativeUploadRoute(
                NativeEffectCarrier.A3,
                0x58,
                NativeUploadPurpose.SCENE,
                H6022EffectUpload,
                H6022_PROFESSIONAL_SCENE_FAMILIES,
            ),
        ),
        scene_route=_h6022_scene_route,
        decode_tree=_reject_opaque_decode,
        parse_scene_body=_parse_h6022_scene,
        catalogue_scene_families=H6022_SCENE_FAMILIES,
        opaque_scene_families=H6022_SCENE_FAMILIES,
    ),
)

_CODEC_BY_ID: Mapping[str, NativeEffectCodec] = {codec.codec_id: codec for codec in NATIVE_EFFECT_CODECS}
_CODEC_BY_TARGET: Mapping[str, NativeEffectCodec] = {codec.canonical_target: codec for codec in NATIVE_EFFECT_CODECS}


def native_effect_codec_for_id(codec_id: str | None) -> NativeEffectCodec | None:
    return None if codec_id is None else _CODEC_BY_ID.get(codec_id)


def native_effect_codec_for_profile(profile: ModelProfile) -> NativeEffectCodec | None:
    codec = native_effect_codec_for_id(profile.native_effect_codec)
    if codec is None:
        codecs = [
            candidate
            for candidate in NATIVE_EFFECT_CODECS
            if candidate.effect_grammar == profile.effect_grammar and not candidate.explicit_profile_required
        ]
        return codecs[0] if len(codecs) == 1 else None
    if codec.effect_grammar != profile.effect_grammar:
        return None
    return codec


def native_effect_codec_for_grammar(grammar: str) -> NativeEffectCodec | None:
    codecs = [codec for codec in NATIVE_EFFECT_CODECS if codec.effect_grammar == grammar]
    return codecs[0] if len(codecs) == 1 else None


def native_effect_codec_for_target(target: str) -> NativeEffectCodec | None:
    codec = _CODEC_BY_TARGET.get(target)
    if codec is not None:
        return codec
    try:
        return native_effect_codec_for_profile(get_profile(target))
    except ValueError:
        return None


def native_effect_codec_for_scene_family(family: int) -> NativeEffectCodec | None:
    codecs = [
        codec
        for codec in NATIVE_EFFECT_CODECS
        if family in codec.catalogue_scene_families or family in codec.opaque_scene_families
    ]
    if len(codecs) > 1:
        raise ValueError("Native scene family is ambiguous across codecs")
    return codecs[0] if codecs else None


def native_effect_codec_for_scene_speed(scene_type: int, payload: bytes) -> NativeEffectCodec | None:
    codecs = [codec for codec in NATIVE_EFFECT_CODECS if codec.scene_speed_type == scene_type]
    if not codecs:
        codecs = [codec for codec in NATIVE_EFFECT_CODECS if codec.scene_speed_type is not None]
    for codec in codecs:
        if codec.validate_layered_payload is None:
            continue
        try:
            codec.validate_layered_payload(payload)
        except ValueError:
            continue
        return codec
    return codecs[0] if len(codecs) == 1 else None


def native_effect_codec_for_content(content: NativeEffect) -> NativeEffectCodec:
    codec = native_effect_codec_for_target(content.model)
    if codec is None:
        raise ValueError("unsupported native effect target")
    return codec


def native_effect_codec_for_tree(tree: Any) -> NativeEffectCodec | None:
    return next(
        (
            codec
            for codec in NATIVE_EFFECT_CODECS
            if isinstance(tree, codec.native_tree_types)
            or any(
                route.families and route.root_type is not None and isinstance(tree, route.root_type)
                for route in codec.routes
            )
        ),
        None,
    )
