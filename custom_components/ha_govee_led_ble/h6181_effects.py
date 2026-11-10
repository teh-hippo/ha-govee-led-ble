"""H6181 palette DIY bodies through their exact-model schema."""

from .const import ModelProfile
from .effect_domain import EffectPair, MultiEffect, SingleEffect
from .generated_protocol_adapter import build_h617a_diy_multi_body, build_h617a_diy_single_body
from .protocol_core import H6181DiyBody, new_child, new_rgb, serialize_native_body
from .transport import fragment_a1_02, fragment_a3


def build_diy(content: SingleEffect | MultiEffect, code: int, profile: ModelProfile) -> list[bytes]:
    if profile.diy_upload_transport == "a3":
        body = (
            build_h617a_diy_single_body(content.family, content.variant, content.speed, list(content.palette))
            if isinstance(content, SingleEffect)
            else build_h617a_diy_multi_body(
                [(pair.family, pair.variant) for pair in content.effects], content.speed, list(content.palette)
            )
        )
        return fragment_a3(4, body)
    if profile.diy_upload_transport != "a1_02" or not 0 <= code <= 255:
        raise ValueError("Legacy palette DIY requires an approved one-byte selector")
    root = H6181DiyBody()
    root.selector = code
    root.family = (
        H6181DiyBody.EffectFamily(content.family)
        if isinstance(content, SingleEffect)
        else H6181DiyBody.EffectFamily.mixed
    )
    root.variant = content.variant if isinstance(content, SingleEffect) else 0
    root.speed = content.speed
    root.len_palette = len(content.palette) * 3
    root.palette = new_child(H6181DiyBody.Palette, root)
    root.palette.colours = [new_rgb(root.palette, rgb) for rgb in content.palette]
    root.components = []
    if isinstance(content, MultiEffect):
        for component in content.effects:
            pair = new_child(H6181DiyBody.EffectPair, root)
            pair.family = H6181DiyBody.EffectFamily(component.family)
            pair.variant = component.variant
            root.components.append(pair)
    root.len_components = len(root.components) * 2
    root.unknown_tail = b""
    return fragment_a1_02(serialize_native_body(root))


def decode_diy(data: bytes) -> SingleEffect | MultiEffect:
    root = H6181DiyBody.from_bytes(data)
    root._read()
    if any(root.unknown_tail) or root.len_components != len(root.components) * 2:
        raise ValueError("Palette DIY has unrepresented trailing data")
    palette = tuple((int(rgb.red), int(rgb.green), int(rgb.blue)) for rgb in root.palette.colours)
    content: SingleEffect | MultiEffect
    if root.family == H6181DiyBody.EffectFamily.mixed:
        if root.variant:
            raise ValueError("Mixed palette DIY variant must be zero")
        content = MultiEffect(
            effects=tuple(EffectPair(int(pair.family), pair.variant) for pair in root.components),
            speed=root.speed,
            palette=palette,
        )
    else:
        if root.components:
            raise ValueError("Single palette DIY cannot contain mixed components")
        content = SingleEffect(int(root.family), root.variant, root.speed, palette)
    from .effect_catalogue import validate_effect_eligibility

    validate_effect_eligibility(content, "H6181")
    return content
