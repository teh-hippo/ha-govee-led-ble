import {
  customEffectCategoryForItem,
  isMyEffectKind,
  type CustomEffectCategory,
  type NewEffectKind,
} from "./effect-editor-model";
import type {
  LibrarySummary,
  ModelEffectCatalogue,
  ModelSku,
} from "./types";
import { compareLabels } from "./ui-utils";
import {
  MULTI_EFFECT_KIND,
  PAINTED_EFFECT_KIND,
  SINGLE_EFFECT_KIND,
  TYPED_MIXED_DIY_KIND,
  TYPED_SINGLE_DIY_KIND,
  isPortableLibraryEffectKind,
} from "./custom-effect-policies";

export interface CustomEffectListContext {
  compatibilities?: import("./types").DeviceCapabilities["effect_compatibilities"];
  model?: ModelSku;
  catalogue?: ModelEffectCatalogue;
  libraryItems: LibrarySummary[];
  staticComposition?: boolean;
}

export type CustomEffectListEntry =
  | {
      kind: "native-diy";
      key: string;
      label: string;
      category: "single-layer" | "multi-layer" | "advanced";
    }
  | {
      kind: "paint";
      key: "template:paint";
      label: "Paint";
      category: "single-layer";
    }
  | {
      kind: "single";
      key: string;
      label: string;
      category: "single-layer";
      family: number;
      variant: number;
    }
  | {
      kind: "music";
      key: string;
      label: string;
      category: "music";
      mode: string;
    }
  | {
      kind: "saved";
      key: string;
      label: string;
      category: Exclude<CustomEffectCategory, "all">;
      item: LibrarySummary;
    };

export function buildCustomEffectEntries(
  context: CustomEffectListContext,
  category: CustomEffectCategory,
): CustomEffectListEntry[] {
  const catalogue = context.catalogue;
  const entries: CustomEffectListEntry[] = [
    ...(catalogue?.templates?.filter((template) =>
      (template.category === "single-layer" || template.category === "multi-layer" || template.category === "advanced") &&
      (template.content.kind === "native_effect" ||
        template.content.kind === "advanced"),
    ).map((template): CustomEffectListEntry => ({
      kind: "native-diy", key: template.id, label: template.label,
      category: template.category === "multi-layer" ? "multi-layer" : template.category === "single-layer" ? "single-layer" : "advanced",
    })) ?? []),
    ...(catalogue?.painted_effects.length
      ? [
          {
            kind: "paint" as const,
            key: "template:paint" as const,
            label: "Paint" as const,
            category: "single-layer" as const,
          },
        ]
      : []),
    ...(catalogue?.effects
      .filter((effect) => effect.category === "single_layer" &&
        !catalogue?.templates?.some(template => template.content.kind === "native_effect" &&
          (template.content.family === effect.family ||
            template.content.layers.length === 1 && template.content.layers[0].type !== "paint" &&
              template.content.layers[0].kind === effect.family)))
      .map(
        (effect): CustomEffectListEntry => ({
          kind: "single",
          key: `template:single:${effect.family}:${effect.variations[0].variant}`,
          label: effect.label,
          category: "single-layer",
          family: effect.family,
          variant: effect.variations[0].variant,
        }),
      ) ?? []),
    ...(catalogue?.music_modes.map(
      (mode): CustomEffectListEntry => ({
        kind: "music",
        key: `template:music:${mode.id}`,
        label: mode.label,
        category: "music",
        mode: mode.id,
      }),
    ) ?? []),
    ...context.libraryItems
      .filter(
        (item) => isMyEffectKind(item.kind) && item.kind !== "video_profile" &&
          !(item.kind === "native_effect" && item.template !== undefined),
      )
      .map(
        (item): CustomEffectListEntry => ({
          kind: "saved",
          key: `saved:${item.id}`,
          label: item.name,
          category: customEffectCategoryForItem(item),
          item,
        }),
      ),
  ];
  return entries
    .filter((entry) => customEffectEntryAvailable(context, entry))
    .filter(
      (entry) =>
        category === "all" ||
        (category === "my-effects" && entry.kind === "saved") ||
        entry.category === category,
    )
    .sort((left, right) => compareLabels(left.label, right.label));
}

export function libraryItemAvailable(
  context: CustomEffectListContext,
  item: LibrarySummary,
): boolean {
  const resolved = context.compatibilities?.[item.id];
  if (resolved?.version === item.version && resolved.state === "compatible") return true;
  if (
    item.model !== undefined &&
    item.model !== context.model &&
    !isPortableLibraryEffectKind(item.kind)
  ) {
    return false;
  }
  if (item.kind === "video_profile") {
    return Boolean(context.catalogue?.video_modes.length);
  }
  return customEffectKindAvailable(context, item.kind);
}

export function customEffectCategoryAvailable(
  context: CustomEffectListContext,
  category: CustomEffectCategory,
): boolean {
  switch (category) {
    case "static":
      return context.staticComposition === true;
    case "all":
      return customEffectsAvailable(context);
    case "music":
      return Boolean(context.catalogue?.music_modes.length);
    case "single-layer":
      return (
        customEffectKindAvailable(context, "native_effect") ||
        customEffectKindAvailable(context, PAINTED_EFFECT_KIND) ||
        customEffectKindAvailable(context, SINGLE_EFFECT_KIND) ||
        customEffectKindAvailable(context, TYPED_SINGLE_DIY_KIND) ||
        customEffectKindAvailable(context, "palette_diy")
      );
    case "multi-layer":
      return (
        Boolean(context.catalogue?.templates?.some(template => template.category === "multi-layer" &&
          template.content.kind === "native_effect")) && context.catalogue?.apply.multi === "supported" ||
        customEffectKindAvailable(context, MULTI_EFFECT_KIND) ||
        customEffectKindAvailable(context, TYPED_MIXED_DIY_KIND)
      );
    case "advanced":
      return (
        customEffectKindAvailable(context, "advanced") ||
        customEffectKindAvailable(context, "workshop")
      );
    case "my-effects":
      return false;
  }
}

export function customEffectKindAvailable(
  context: CustomEffectListContext,
  kind: string,
): boolean {
  if (kind === "static_rgb") return context.staticComposition === true;
  const catalogue = context.catalogue;
  if (!catalogue) {
    return false;
  }
  if (kind === "native_effect") {
    return catalogue.workflows.some((workflow) => workflow.content_kind === kind) &&
      (catalogue.apply.single !== "unsupported" || catalogue.apply.painted !== "unsupported");
  }
  if (kind === PAINTED_EFFECT_KIND) {
    return (
      Boolean(catalogue.painted_effects.length) &&
      catalogue.apply.painted !== "unsupported"
    );
  }
  if (kind === SINGLE_EFFECT_KIND) {
    return (
      !catalogue.workflows.some(
        (workflow) => workflow.content_kind === TYPED_SINGLE_DIY_KIND,
      ) &&
      Boolean(catalogue.effects.length) &&
      catalogue.apply.single !== "unsupported"
    );
  }
  if (kind === TYPED_SINGLE_DIY_KIND) {
    return (
      catalogue.workflows.some((workflow) => workflow.content_kind === kind) &&
      Boolean(catalogue.effects.length) &&
      catalogue.apply.single !== "unsupported"
    );
  }
  if (kind === "palette_diy") {
    return (
      Boolean(catalogue.effects.length) &&
      catalogue.apply.palette_diy !== "unsupported"
    );
  }
  if (kind === MULTI_EFFECT_KIND) {
    return (
      !catalogue.workflows.some(
        (workflow) => workflow.content_kind === TYPED_MIXED_DIY_KIND ||
          workflow.id === "multi" && workflow.content_kind === "native_effect",
      ) &&
      catalogue.supports.multi !== "unsupported" &&
      catalogue.apply.multi !== "unsupported"
    );
  }
  if (kind === TYPED_MIXED_DIY_KIND) {
    return (
      catalogue.workflows.some((workflow) => workflow.content_kind === kind) &&
      catalogue.supports.multi !== "unsupported" &&
      catalogue.apply.multi !== "unsupported"
    );
  }
  if (kind === "music_profile") {
    return Boolean(catalogue.music_modes.length);
  }
  if (kind === "workshop") {
    return (
      catalogue.supports.workshop !== "unsupported" &&
      catalogue.apply.workshop !== "unsupported"
    );
  }
  return catalogue.supports.advanced !== "unsupported";
}

export function newEffectKindForCategory(
  context: CustomEffectListContext,
  category: CustomEffectCategory,
): NewEffectKind | undefined {
  if (category === "static") return context.staticComposition ? "static_rgb" : undefined;
  const nativeWorkflow = category === "single-layer" ? "single" :
    category === "multi-layer" ? "multi" : category === "advanced" ? "advanced" : undefined;
  if (context.catalogue?.workflows.some((workflow) =>
    workflow.id === nativeWorkflow && workflow.content_kind === "native_effect")) {
    return undefined;
  }
  if (category === "single-layer") {
    if (customEffectKindAvailable(context, SINGLE_EFFECT_KIND)) {
      return SINGLE_EFFECT_KIND;
    }
    if (customEffectKindAvailable(context, TYPED_SINGLE_DIY_KIND)) {
      return TYPED_SINGLE_DIY_KIND;
    }
    if (customEffectKindAvailable(context, "palette_diy")) {
      return "palette_diy";
    }
    return customEffectKindAvailable(context, PAINTED_EFFECT_KIND)
      ? PAINTED_EFFECT_KIND
      : undefined;
  }
  if (category === "multi-layer") {
    if (customEffectKindAvailable(context, MULTI_EFFECT_KIND)) {
      return MULTI_EFFECT_KIND;
    }
    return customEffectKindAvailable(context, TYPED_MIXED_DIY_KIND)
      ? TYPED_MIXED_DIY_KIND
      : undefined;
  }
  if (category === "advanced") {
    return context.catalogue?.advanced_create !== false &&
      customEffectKindAvailable(context, "advanced")
      ? "advanced"
      : undefined;
  }
  return undefined;
}

function customEffectEntryAvailable(
  context: CustomEffectListContext,
  entry: CustomEffectListEntry,
): boolean {
  switch (entry.kind) {
    case "native-diy":
      return customEffectCategoryAvailable(context, entry.category);
    case "paint":
      return customEffectKindAvailable(context, PAINTED_EFFECT_KIND);
    case "single":
      return customEffectKindAvailable(
        context,
        customEffectKindAvailable(context, SINGLE_EFFECT_KIND)
          ? SINGLE_EFFECT_KIND
          : customEffectKindAvailable(context, TYPED_SINGLE_DIY_KIND)
            ? TYPED_SINGLE_DIY_KIND
            : "palette_diy",
      );
    case "music":
      return customEffectKindAvailable(context, "music_profile");
    case "saved":
      return libraryItemAvailable(context, entry.item);
  }
}

function customEffectsAvailable(context: CustomEffectListContext): boolean {
  const catalogue = context.catalogue;
  return Boolean(
    catalogue &&
      (catalogue.painted_effects.length ||
        catalogue.effects.length ||
        catalogue.music_modes.length ||
        catalogue.templates?.some((template) =>
          template.content.kind === "native_effect" ||
          template.content.kind === "advanced") ||
        catalogue.supports.advanced !== "unsupported"),
  );
}
