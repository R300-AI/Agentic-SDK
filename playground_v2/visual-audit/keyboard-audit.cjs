const { chromium } = require("playwright");

async function main() {
  const baseUrl = process.env.PLAYGROUND_V2_URL || "http://127.0.0.1:5051";
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  await page.goto(`${baseUrl}/playground/run?mode=aihub_readonly`, { waitUntil: "networkidle" });

  let focusedTrustToggle = false;
  for (let index = 0; index < 20; index += 1) {
    await page.keyboard.press("Tab");
    focusedTrustToggle = await page.locator("[data-trust-toggle]").evaluate((element) => element === document.activeElement);
    if (focusedTrustToggle) {
      break;
    }
  }

  if (!focusedTrustToggle) {
    throw new Error("Trust basis toggle was not reachable by keyboard tab navigation.");
  }

  await page.keyboard.press("Enter");
  const expanded = await page.locator("[data-trust-toggle]").getAttribute("aria-expanded");
  const panelHidden = await page.locator("[data-trust-panel]").evaluate((element) => element.hidden);

  await browser.close();

  if (expanded !== "true" || panelHidden) {
    throw new Error("Trust basis panel did not expand from keyboard activation.");
  }

  console.log("keyboard-audit ok: trust basis toggle is keyboard reachable and expandable");
}

main().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
