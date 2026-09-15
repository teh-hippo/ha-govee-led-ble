import {
  customEffectCategoryForKind,
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

export interface CustomEffectListContext {
  model?: ModelSku;
  catalogue?: ModelEffectCatalogue;
  libraryItems: LibrarySummary[];
}

export type CustomEffectListEntry =
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
      .filter((effect) => effect.category === "single_layer")
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
        (item) => isMyEffectKind(item.kind) && item.kind !== "video_profile",
      )
      .map(
        (item): CustomEffectListEntry => ({
          kind: "saved",
          key: `saved:${item.id}`,
          label: item.name,
          category: customEffectCategoryForKind(item.kind),
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
  const modelIndependentContent = [
    "h617a_painted",
    "h617a_single",
    "h617a_multi",
  ].includes(item.kind);
  if (
    item.model !== undefined &&
    item.model !== context.model &&
    !modelIndependentContent
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
    case "all":
      return customEffectsAvailable(context);
    case "music":
      return Boolean(context.catalogue?.music_modes.length);
    case "single-layer":
      return (
        customEffectKindAvailable(context, "h617a_painted") ||
        customEffectKindAvailable(context, "h617a_single") ||
        customEffectKindAvailable(context, "h6179_single_diy") ||
        customEffectKindAvailable(context, "palette_diy")
      );
    case "multi-layer":
      return (
        customEffectKindAvailable(context, "h617a_multi") ||
        customEffectKindAvailable(context, "h6179_mixed_diy")
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
  const catalogue = context.catalogue;
  if (!catalogue) {
    return false;
  }
  if (kind === "h617a_painted") {
    return (
      Boolean(catalogue.painted_effects.length) &&
      catalogue.apply.painted !== "unsupported"
    );
  }
  if (kind === "h617a_single") {
    return (
      !catalogue.workflows.some(
        (workflow) => workflow.content_kind === "h6179_single_diy",
      ) &&
      Boolean(catalogue.effects.length) &&
      catalogue.apply.single !== "unsupported"
    );
  }
  if (kind === "h6179_single_diy") {
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
  if (kind === "h617a_multi") {
    return (
      !catalogue.workflows.some(
        (workflow) => workflow.content_kind === "h6179_mixed_diy",
      ) &&
      catalogue.supports.multi !== "unsupported" &&
      catalogue.apply.multi !== "unsupported"
    );
  }
  if (kind === "h6179_mixed_diy") {
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
  if (category === "single-layer") {
    if (customEffectKindAvailable(context, "h617a_single")) {
      return "h617a_single";
    }
    if (customEffectKindAvailable(context, "h6179_single_diy")) {
      return "h6179_single_diy";
    }
    if (customEffectKindAvailable(context, "palette_diy")) {
      return "palette_diy";
    }
    return customEffectKindAvailable(context, "h617a_painted")
      ? "h617a_painted"
      : undefined;
  }
  if (category === "multi-layer") {
    if (customEffectKindAvailable(context, "h617a_multi")) {
      return "h617a_multi";
    }
    return customEffectKindAvailable(context, "h6179_mixed_diy")
      ? "h6179_mixed_diy"
      : undefined;
  }
  if (category === "advanced") {
    return customEffectKindAvailable(context, "advanced")
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
    case "paint":
      return customEffectKindAvailable(context, "h617a_painted");
    case "single":
      return customEffectKindAvailable(
        context,
        customEffectKindAvailable(context, "h617a_single")
          ? "h617a_single"
          : customEffectKindAvailable(context, "h6179_single_diy")
            ? "h6179_single_diy"
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
        catalogue.supports.advanced !== "unsupported"),
  );
}
