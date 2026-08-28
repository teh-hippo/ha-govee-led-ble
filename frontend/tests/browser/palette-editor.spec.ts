import { expect, test, type Locator, type Page } from "@playwright/test";

const CONTEXTS = [
  "direct-context",
  "custom-context",
  "advanced-context",
] as const;

test.beforeEach(async ({ page }) => {
  await page.goto("/tests/browser/fixtures/palette-editor.html");
});

for (const contextName of CONTEXTS) {
  test(`${contextName} activates an existing colour from touch completion`, async ({
    page,
  }) => {
    const context = page.getByTestId(contextName);
    const swatch = context.getByRole("button", {
      name: /Edit colour 1,/,
    });

    await touchItem(swatch);

    await expect(
      context.getByRole("dialog", { name: "Edit colour" }),
    ).toBeVisible();
    await expect(
      context.getByRole("button", { name: "Remove colour 1" }),
    ).toBeVisible();
  });
}

test("touch compatibility clicks do not double-activate colours", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  const swatch = context.getByRole("button", {
    name: /Edit colour 1,/,
  });

  await touchItem(swatch, { compatibilityClick: true });

  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toBeVisible();
  await expect(context.getByRole("listitem")).toHaveCount(3);
  await expect(
    context.getByRole("button", { name: "Remove colour 1" }),
  ).toBeVisible();
});

test("secondary touches do not replace the active palette gesture", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  const swatch = context.getByRole("button", {
    name: /Edit colour 1,/,
  });

  await swatch.evaluate((element) => {
    const rect = element.getBoundingClientRect();
    const event = {
      bubbles: true,
      composed: true,
      clientX: rect.left + rect.width / 2,
      clientY: rect.top + rect.height / 2,
      pointerType: "touch",
    };
    element.dispatchEvent(
      new PointerEvent("pointerdown", {
        ...event,
        buttons: 1,
        isPrimary: true,
        pointerId: 7,
      }),
    );
    element.dispatchEvent(
      new PointerEvent("pointerdown", {
        ...event,
        buttons: 1,
        isPrimary: false,
        pointerId: 8,
      }),
    );
    element.dispatchEvent(
      new PointerEvent("pointerup", {
        ...event,
        buttons: 0,
        isPrimary: true,
        pointerId: 7,
      }),
    );
  });
  await settle(page);

  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toBeVisible();
});

test("existing and added colours can be changed, reopened, and removed", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  let first = context.getByRole("button", {
    name: /Edit colour 1,/,
  });

  await touchItem(first, { compatibilityClick: true });
  await context.getByRole("button", { name: "Use #ff453a" }).tap();
  first = context.getByRole("button", {
    name: "Edit colour 1, #ff453a. Drag to reorder or use arrow keys.",
  });
  await expect(first).toBeVisible();

  await touchItem(first, { compatibilityClick: true });
  await touchItem(
    context.getByRole("button", { name: "Remove colour 1" }),
    { compatibilityClick: true },
  );
  await expect(context.getByRole("listitem")).toHaveCount(2);

  await context.getByRole("button", { name: "Add colour" }).tap();
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toBeVisible();
  await page.getByTestId("outside").tap();
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toHaveCount(0);

  const added = context.getByRole("button", {
    name: /Edit colour 3,/,
  });
  await touchItem(added, { compatibilityClick: true });
  await context.getByRole("button", { name: "Use #ff9f0a" }).tap();
  await expect(
    context.getByRole("button", {
      name: "Edit colour 3, #ff9f0a. Drag to reorder or use arrow keys.",
    }),
  ).toBeVisible();
});

test("touch cancellation and vertical movement do not activate colours", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  const swatch = context.getByRole("button", {
    name: /Edit colour 1,/,
  });

  await touchItem(swatch, { cancelled: true });
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toHaveCount(0);

  await touchItem(swatch, {
    compatibilityClick: true,
    move: { x: 0, y: 24 },
  });
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toHaveCount(0);
});

test("keyboard activation remains available after a touch without click", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  const swatch = context.getByRole("button", {
    name: /Edit colour 1,/,
  });

  await touchItem(swatch);
  await page.keyboard.press("Escape");
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toHaveCount(0);

  await swatch.focus();
  await swatch.press("Enter");
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toBeVisible();
});

test("native WebKit drag-and-drop reorders without activating a colour", async ({
  page,
}) => {
  const context = page.getByTestId("direct-context");
  const first = context.getByRole("button", {
    name: "Edit colour 1, #ff0000. Drag to reorder or use arrow keys.",
  });
  const second = context.getByRole("button", {
    name: "Edit colour 2, #00ff00. Drag to reorder or use arrow keys.",
  });

  await first.dragTo(second);

  await expect(
    context.getByRole("button", {
      name: "Edit colour 1, #00ff00. Drag to reorder or use arrow keys.",
    }),
  ).toBeVisible();
  await expect(
    context.getByRole("dialog", { name: "Edit colour" }),
  ).toHaveCount(0);
});

interface TouchItemOptions {
  cancelled?: boolean;
  compatibilityClick?: boolean;
  move?: {
    x: number;
    y: number;
  };
}

async function touchItem(
  item: Locator,
  options: TouchItemOptions = {},
): Promise<void> {
  await item.evaluate(
    (
      element,
      {
        cancelled = false,
        compatibilityClick = false,
        move = { x: 0, y: 0 },
      },
    ) => {
      const rect = element.getBoundingClientRect();
      const start = {
        bubbles: true,
        composed: true,
        isPrimary: true,
        pointerId: 7,
        pointerType: "touch",
        clientX: rect.left + rect.width / 2,
        clientY: rect.top + rect.height / 2,
      };
      element.dispatchEvent(
        new PointerEvent("pointerdown", {
          ...start,
          buttons: 1,
        }),
      );
      if (move.x !== 0 || move.y !== 0) {
        element.dispatchEvent(
          new PointerEvent("pointermove", {
            ...start,
            buttons: 1,
            clientX: start.clientX + move.x,
            clientY: start.clientY + move.y,
          }),
        );
      }
      element.dispatchEvent(
        new PointerEvent(cancelled ? "pointercancel" : "pointerup", {
          ...start,
          buttons: 0,
          clientX: start.clientX + move.x,
          clientY: start.clientY + move.y,
        }),
      );
      if (compatibilityClick && !cancelled) {
        element.dispatchEvent(
          new MouseEvent("click", {
            bubbles: true,
            composed: true,
            detail: 1,
          }),
        );
      }
    },
    options,
  );
  await settle(pageFor(item));
}

function pageFor(locator: Locator): Page {
  return locator.page();
}

async function settle(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}
