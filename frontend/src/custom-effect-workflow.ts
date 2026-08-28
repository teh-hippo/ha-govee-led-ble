import {
  customEffectCategoryAvailable,
  type CustomEffectListContext,
} from "./custom-effect-list";
import {
  type CustomEffectCategory,
} from "./effect-editor-model";

const CATEGORY_PRIORITY: readonly Exclude<
  CustomEffectCategory,
  "all"
>[] = [
  "single-layer",
  "multi-layer",
  "music",
  "advanced",
];

const CATEGORY_LABELS: Readonly<
  Record<CustomEffectCategory, string>
> = {
  all: "All",
  "my-effects": "My Effects",
  "multi-layer": "Multi-Layered",
  music: "Reactive",
  "single-layer": "Effects",
  advanced: "Advanced",
};

const CATEGORY_DISPLAY_ORDER: readonly CustomEffectCategory[] = [
  "single-layer",
  "multi-layer",
  "music",
  "advanced",
];

export function customEffectCategoryLabel(
  category: CustomEffectCategory,
): string {
  return CATEGORY_LABELS[category];
}

export function customEffectCategories(
  context: CustomEffectListContext,
): { category: CustomEffectCategory; label: string }[] {
  return CATEGORY_DISPLAY_ORDER.filter((category) =>
    customEffectCategoryAvailable(context, category),
  ).map((category) => ({
    category,
    label: customEffectCategoryLabel(category),
  }));
}

export function defaultCustomEffectCategory(
  context: CustomEffectListContext,
): CustomEffectCategory {
  return (
    CATEGORY_PRIORITY.find((category) =>
      customEffectCategoryAvailable(context, category),
    ) ?? "single-layer"
  );
}
