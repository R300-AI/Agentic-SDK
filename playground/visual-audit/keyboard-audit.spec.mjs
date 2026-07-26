import { expect, test } from "@playwright/test";

const baseUrl = process.env.PLAYGROUND_URL || "http://127.0.0.1";

test("Runner trust basis toggle is keyboard reachable and expandable", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto(`${baseUrl}/playground/run?mode=aihub_readonly`);

  let focusedTrustToggle = false;
  for (let index = 0; index < 20; index += 1) {
    await page.keyboard.press("Tab");
    focusedTrustToggle = await page.locator("[data-trust-toggle]").evaluate((element) => element === document.activeElement);
    if (focusedTrustToggle) {
      break;
    }
  }

  expect(focusedTrustToggle).toBe(true);
  await page.keyboard.press("Enter");
  await expect(page.locator("[data-trust-toggle]")).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator("[data-trust-panel]")).toBeVisible();
});
