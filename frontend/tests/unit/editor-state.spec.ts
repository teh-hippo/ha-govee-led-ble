import { expect, test } from "vitest";

import {
  editorActionDescriptors,
  editorActionOrder,
  editorOwnerMatches,
  newEditorSourceSelected,
  reactiveEffectSelectorVisible,
  type EditorActionContext,
  type EditorSource,
} from "../../src/editor-state";

const catalogue: EditorSource = {
  kind: "catalogue",
  owner: { section: "custom", category: "single-layer" },
  selectionIdentity: "template:paint",
  label: "Paint",
};
const saved: EditorSource = {
  kind: "saved",
  owner: { section: "custom", category: "music" },
  itemId: "saved-a",
};

function context(
  update: Partial<EditorActionContext> = {},
): EditorActionContext {
  return {
    resetAvailable: true,
    resetDirty: false,
    autoSaveEnabled: false,
    autoSaveFailed: false,
    canSave: true,
    canMutate: true,
    busy: false,
    ...update,
  };
}

test("editor action descriptors follow source, state, and exact order", () => {
  expect(
    editorActionOrder(
      editorActionDescriptors(catalogue, context()),
    ),
  ).toEqual(["saveAs"]);
  expect(
    editorActionOrder(
      editorActionDescriptors(
        catalogue,
        context({
          resetDirty: true,
          defaultDirty: true,
          liveApplyEnabled: false,
          canApply: true,
        }),
      ),
    ),
  ).toEqual(["apply", "saveAs", "reset", "save"]);

  const newActions = editorActionDescriptors(
    {
      kind: "new",
      owner: { section: "custom", category: "advanced" },
    },
    context(),
  );
  expect(editorActionOrder(newActions)).toEqual(["reset", "save"]);
  expect(newActions.find(({ id }) => id === "reset")).toMatchObject({
    style: "secondary",
    visible: true,
    enabled: false,
  });

  expect(
    editorActionOrder(
      editorActionDescriptors(
        saved,
        context({ resetDirty: true, autoSaveEnabled: true }),
      ),
    ),
  ).toEqual(["saveAs", "reset", "delete"]);
  expect(
    editorActionDescriptors(
      saved,
      context({ autoSaveEnabled: true, autoSaveFailed: true }),
    ).find(({ id }) => id === "save"),
  ).toMatchObject({ visible: true, enabled: true, style: "primary" });

  const sceneActions = editorActionDescriptors(
    {
      kind: "scene",
      owner: { section: "scenes" },
      itemId: "scene-a",
    },
    context({ resetDirty: true }),
  );
  expect(editorActionOrder(sceneActions)).toEqual([
    "saveAs",
    "reset",
    "cancel",
    "delete",
    "save",
  ]);
});

test("busy and read-only state disable visible mutations", () => {
  const actions = editorActionDescriptors(
    saved,
    context({ resetDirty: true, canMutate: false, busy: true }),
  );
  expect(
    actions.filter(({ visible }) => visible).every(({ enabled }) => !enabled),
  ).toBe(true);
});

test("editor ownership rejects content from another category or section", () => {
  expect(editorOwnerMatches(catalogue, "custom", "single-layer")).toBe(true);
  expect(editorOwnerMatches(catalogue, "custom", "music")).toBe(false);
  expect(editorOwnerMatches(catalogue, "video", "single-layer")).toBe(false);
  expect(
    editorOwnerMatches(
      {
        kind: "catalogue",
        owner: { section: "video" },
        selectionIdentity: "template:video:movie",
        label: "Movie",
      },
      "video",
      "single-layer",
    ),
  ).toBe(true);
});

test("New selection follows its explicit custom category owner", () => {
  for (const category of [
    "single-layer",
    "multi-layer",
    "music",
    "advanced",
  ] as const) {
    const source: EditorSource = {
      kind: "new",
      owner: { section: "custom", category },
    };
    expect(newEditorSourceSelected(source, category)).toBe(true);
    expect(
      newEditorSourceSelected(
        source,
        category === "single-layer" ? "music" : "single-layer",
      ),
    ).toBe(false);
  }
  expect(newEditorSourceSelected(saved, "music")).toBe(false);
});

test("Reactive selector belongs to New and saved drafts, not catalogue templates", () => {
  expect(
    reactiveEffectSelectorVisible({
      kind: "new",
      owner: { section: "custom", category: "music" },
    }),
  ).toBe(true);
  expect(reactiveEffectSelectorVisible(saved)).toBe(true);
  expect(reactiveEffectSelectorVisible(catalogue)).toBe(false);
});
