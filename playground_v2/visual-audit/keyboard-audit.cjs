const { chromium } = require("playwright");

async function main() {
  const baseUrl = process.env.PLAYGROUND_V2_URL || "http://127.0.0.1:5051";
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } });

  await page.goto(`${baseUrl}/playground/run?mode=aihub_readonly`, { waitUntil: "networkidle" });

  let focusedSubmitButton = false;
  for (let index = 0; index < 20; index += 1) {
    await page.keyboard.press("Tab");
    focusedSubmitButton = await page.locator("[data-input-composer] button[type='submit']").evaluate((element) => element === document.activeElement);
    if (focusedSubmitButton) {
      break;
    }
  }

  if (!focusedSubmitButton) {
    throw new Error("Runner submit button was not reachable by keyboard tab navigation.");
  }

  const statusRole = await page.locator("[data-run-status]").getAttribute("role");
  const trustToggleCount = await page.locator("[data-trust-toggle]").count();

  await browser.close();

  if (statusRole !== "status" || trustToggleCount !== 0) {
    throw new Error("Runner execution details must stay in the status line, not a trust panel component.");
  }

  console.log("keyboard-audit ok: runner submit is keyboard reachable and execution status stays inline");
}

main().catch(async (error) => {
  console.error(error);
  process.exit(1);
});
