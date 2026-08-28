import { expect, test, type Locator, type Page } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.goto("/tests/browser/fixtures/palette-editor.html");
});

test("painted segment taps finish with a committed interaction", async ({
  page,
}) => {
  const context = page.getByTestId("painted-context");

  await context.getByRole("button", { name: "Segment 1, off" }).tap();

  await expect(context.getByTestId("painted-events")).toHaveText(
    JSON.stringify([
      { index: 0, interaction: "changing" },
      { index: 0, interaction: "committed" },
    ]),
  );
});

test("painted segment drags commit once and release for the next gesture", async ({
  page,
}) => {
  const context = page.getByTestId("painted-context");
  const first = context.locator('[data-segment="0"]');
  const third = context.getByRole("button", { name: "Segment 3, off" });

  await mouseDrag(page, first, third);

  const firstEvents = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(firstEvents[0]).toEqual({ index: 0, interaction: "changing" });
  expect(firstEvents.at(-1)).toEqual({
    index: 2,
    interaction: "committed",
  });
  expect(
    firstEvents.filter((event) => event.interaction === "committed"),
  ).toHaveLength(1);

  await context.getByRole("button", { name: "Segment 5, off" }).tap();
  const nextEvents = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(nextEvents.at(-1)).toEqual({
    index: 4,
    interaction: "committed",
  });
});

test("cancelled painted strokes commit applied changes and release capture", async ({
  page,
}) => {
  const context = page.getByTestId("painted-context");
  const first = context.locator('[data-segment="0"]');
  await first.scrollIntoViewIfNeeded();
  const box = await first.boundingBox();
  expect(box).not.toBeNull();
  await page.evaluate(() => {
    const state = window as Window & { paintPointerId?: number };
    state.paintPointerId = undefined;
    window.addEventListener(
      "pointerdown",
      (event) => {
        state.paintPointerId = event.pointerId;
      },
      { capture: true, once: true },
    );
  });

  await page.mouse.move(
    box!.x + box!.width / 2,
    box!.y + box!.height / 2,
  );
  await page.mouse.down();
  const pointerId = await page.evaluate(
    () => (window as Window & { paintPointerId?: number }).paintPointerId,
  );
  expect(pointerId).toBeDefined();
  await first.dispatchEvent("pointercancel", {
    bubbles: true,
    buttons: 0,
    composed: true,
    isPrimary: true,
    pointerId,
    pointerType: "mouse",
  });
  await page.mouse.up();

  await expect(context.getByTestId("painted-events")).toHaveText(
    JSON.stringify([
      { index: 0, interaction: "changing" },
      { index: 0, interaction: "committed" },
    ]),
  );
  await context.getByRole("button", { name: "Segment 2, off" }).tap();
  const events = await jsonOutput<
    Array<{ index: number; interaction: string }>
  >(context.getByTestId("painted-events"));
  expect(events.at(-1)).toEqual({
    index: 1,
    interaction: "committed",
  });
});

test("cancelled multi-effect touch drags do not poison the next reorder", async ({
  page,
}) => {
  const context = page.getByTestId("multi-context");
  const first = context.getByRole("button", {
    name: /Reorder Layer 1/,
  });
  const second = context.getByRole("button", {
    name: /Reorder Layer 2/,
  });

  await touchDrag(first, second, true);
  await expect(context.getByTestId("multi-order")).toHaveText("[2,3,4]");

  await touchDrag(first, second, false);
  await expect(context.getByTestId("multi-order")).toHaveText("[3,2,4]");
});

test("multi-effect row menus dismiss outside and restore focus on Escape", async ({
  page,
}) => {
  const context = page.getByTestId("multi-context");
  const firstMenu = context.getByLabel("Layer actions for Layer 1");

  await firstMenu.tap();
  await expect(context.getByRole("button", { name: "Remove" })).toBeVisible();
  await page.getByTestId("outside").tap();
  await expect(context.getByRole("button", { name: "Remove" })).toHaveCount(0);

  await firstMenu.tap();
  await firstMenu.press("Escape");
  await expect(context.getByRole("button", { name: "Remove" })).toHaveCount(0);
  await expect(firstMenu).toBeFocused();
});

test("applied-area pointer drags emit live updates and one commit", async ({
  page,
}) => {
  const context = page.getByTestId("area-context");
  const right = context.getByRole("slider", {
    name: "Applied area right edge",
  });
  await right.scrollIntoViewIfNeeded();
  const box = await right.boundingBox();
  expect(box).not.toBeNull();

  await page.mouse.move(
    box!.x + box!.width / 2,
    box!.y + box!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    box!.x + box!.width / 2 + 36,
    box!.y + box!.height / 2,
    { steps: 3 },
  );
  await page.mouse.up();

  const interactions = await jsonOutput<string[]>(
    context.getByTestId("area-events"),
  );
  expect(interactions).toContain("changing");
  expect(interactions.at(-1)).toBe("committed");
  expect(
    interactions.filter((interaction) => interaction === "committed"),
  ).toHaveLength(1);
});

test("native colour input separates live input from committed change", async ({
  page,
}) => {
  const context = page.getByTestId("colour-context");
  const input = context.getByRole("textbox", { name: "Custom colour" });

  await input.fill("#123456");
  await expect(context.getByTestId("colour-events")).toHaveText(
    JSON.stringify([
      {
        colour: [18, 52, 86],
        type: "colour-changing",
      },
      {
        colour: [18, 52, 86],
        type: "colour-changed",
      },
    ]),
  );
  await input.blur();
  await expect(context.getByTestId("colour-events")).toHaveText(
    JSON.stringify([
      {
        colour: [18, 52, 86],
        type: "colour-changing",
      },
      {
        colour: [18, 52, 86],
        type: "colour-changed",
      },
    ]),
  );
});

test("information popovers stay within the mobile viewport and dismiss", async ({
  page,
}) => {
  const context = page.getByTestId("info-context");
  const trigger = context.getByRole("button", {
    name: "WebKit information",
  });
  const note = context.getByRole("note", {
    name: "WebKit information",
  });

  await trigger.scrollIntoViewIfNeeded();
  await trigger.tap();
  await expect(note).toBeVisible();
  await expect(trigger).toHaveAttribute("aria-expanded", "true");
  await assertWithinViewport(page, note);

  await page.setViewportSize({ width: 320, height: 480 });
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(note).not.toBeVisible();

  await page.setViewportSize({ width: 393, height: 659 });
  await trigger.scrollIntoViewIfNeeded();
  await trigger.tap();
  await expect(note).toBeVisible();
  await page.getByTestId("outside").tap();
  await expect(trigger).toHaveAttribute("aria-expanded", "false");
  await expect(note).not.toBeVisible();
});

async function mouseDrag(
  page: Page,
  source: Locator,
  target: Locator,
): Promise<void> {
  await source.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await page.mouse.move(
    sourceBox!.x + sourceBox!.width / 2,
    sourceBox!.y + sourceBox!.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    targetBox!.x + targetBox!.width / 2,
    targetBox!.y + targetBox!.height / 2,
    { steps: 4 },
  );
  await page.mouse.up();
}

async function touchDrag(
  source: Locator,
  target: Locator,
  cancelled: boolean,
): Promise<void> {
  await source.scrollIntoViewIfNeeded();
  const sourceBox = await source.boundingBox();
  const targetBox = await target.boundingBox();
  expect(sourceBox).not.toBeNull();
  expect(targetBox).not.toBeNull();
  await source.evaluate(
    (
      element,
      { cancelled, sourceBox, targetBox },
    ) => {
      const start = {
        bubbles: true,
        composed: true,
        isPrimary: true,
        pointerId: 17,
        pointerType: "touch",
        clientX: sourceBox.x + sourceBox.width / 2,
        clientY: sourceBox.y + sourceBox.height / 2,
      };
      const end = {
        ...start,
        clientX: targetBox.x + targetBox.width / 2,
        clientY: targetBox.y + targetBox.height / 2,
      };
      element.dispatchEvent(
        new PointerEvent("pointerdown", {
          ...start,
          buttons: 1,
        }),
      );
      element.dispatchEvent(
        new PointerEvent("pointermove", {
          ...end,
          buttons: 1,
        }),
      );
      element.dispatchEvent(
        new PointerEvent(cancelled ? "pointercancel" : "pointerup", {
          ...end,
          buttons: 0,
        }),
      );
    },
    {
      cancelled,
      sourceBox: sourceBox!,
      targetBox: targetBox!,
    },
  );
  await settle(source.page());
}

async function jsonOutput<T>(output: Locator): Promise<T> {
  return JSON.parse((await output.textContent()) ?? "null") as T;
}

async function assertWithinViewport(
  page: Page,
  element: Locator,
): Promise<void> {
  await expect
    .poll(async () => {
      const box = await element.boundingBox();
      const viewport = page.viewportSize();
      return (
        box !== null &&
        viewport !== null &&
        box.x >= 0 &&
        box.y >= 0 &&
        box.x + box.width <= viewport.width &&
        box.y + box.height <= viewport.height
      );
    })
    .toBe(true);
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}
