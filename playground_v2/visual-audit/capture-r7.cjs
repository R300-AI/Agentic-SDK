const { chromium } = require("playwright");

const baseUrl = process.env.PLAYGROUND_V2_URL || "http://127.0.0.1:5051";
const pages = [
  ["entry-desktop-r7.png", "/playground/", { width: 1440, height: 960 }],
  ["builder-desktop-r7.png", "/playground/builder", { width: 1440, height: 960 }],
  ["runner-desktop-r7.png", "/playground/run?mode=aihub_readonly", { width: 1440, height: 960 }],
  ["entry-mobile-r7.png", "/playground/", { width: 390, height: 844 }],
  ["builder-mobile-r7.png", "/playground/builder", { width: 390, height: 844 }],
  ["runner-mobile-r7.png", "/playground/run?mode=aihub_readonly", { width: 390, height: 844 }],
];

async function main() {
  const browser = await chromium.launch();
  for (const [fileName, path, viewport] of pages) {
    const page = await browser.newPage({ viewport });
    await page.goto(`${baseUrl}${path}`, { waitUntil: "networkidle" });
    await page.screenshot({ path: `playground_v2/visual-audit/${fileName}`, fullPage: true });
    await page.close();
    console.log(`captured ${fileName}`);
  }
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
