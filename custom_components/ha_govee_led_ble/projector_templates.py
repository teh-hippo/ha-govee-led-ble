"""Explicit authoring defaults for native projector optics."""

from dataclasses import replace

from .effect_catalogue_models import CatalogueTemplate
from .native_effect import NativeEffect
from .projector import ProjectorLayer, ProjectorSource, ProjectorStars


def projector_templates() -> tuple[CatalogueTemplate, ...]:
    palette = ((0, 180, 255), (140, 0, 255))
    source = ProjectorSource(True, 100, 1, 50, palette)
    stars = ProjectorStars(False, 100, False, 50, False, 50)
    layer = ProjectorLayer(10, 0, source, None, stars)
    templates = []
    for preset, label in enumerate(
        (
            "Colour fade",
            "Coarse fade",
            "Fine fade",
            "Colour breathe",
            "Coarse breathe",
            "Fine breathe",
            "Colour flash",
            "Coarse flash",
            "Fine flash",
            "Star flicker",
            "Star movement",
            "Aurora and flicker",
            "Aurora and movement",
        ),
        1,
    ):
        pattern = (preset - 1) // 3 + 1 if preset <= 9 else 4
        coarse = replace(source, pattern=pattern)
        fine = None
        selected_stars = stars
        if preset <= 9 and preset % 3 != 1:
            fine = replace(coarse, enabled=preset % 3 == 0)
            coarse = replace(coarse, enabled=preset % 3 == 2)
        if preset >= 10:
            selected_stars = replace(
                stars, enabled=True, flicker_enabled=preset in (10, 12), movement_enabled=preset in (11, 13)
            )
        if preset in (12, 13):
            coarse = replace(source, pattern=1 if preset == 12 else 2)
            fine = replace(source, pattern=2 if preset == 12 else 1)
        content = NativeEffect(
            model="H6093",
            family=712,
            layers=(),
            projector_layers=(replace(layer, coarse=coarse, fine=fine, stars=selected_stars),),
            preset_id=preset,
        )
        templates.append(CatalogueTemplate(f"template:projector:{preset}", label, "single-layer", content))
    templates.append(
        CatalogueTemplate(
            "template:projector:advanced",
            "Projector layers",
            "advanced",
            NativeEffect(
                model="H6093",
                family=712,
                layers=(),
                projector_layers=(replace(layer, fine=replace(source, palette=((255, 255, 255),))),),
            ),
        )
    )
    return tuple(templates)
