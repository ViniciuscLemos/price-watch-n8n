// Opens the workflow in the n8n editor, runs it by hand and saves screenshots.
// The owner below only exists inside the throwaway CI container.
import { chromium } from 'playwright';

const out = process.argv[2] ?? 'shots';
const base = 'http://localhost:5678';
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1440, height: 860 }, deviceScaleFactor: 2 });
const shot = (name) => page.screenshot({ path: `${out}/${name}.png` });

try {
  const setup = await page.request.post(`${base}/rest/owner/setup`, {
    data: { email: 'ci@example.com', firstName: 'CI', lastName: 'Bot', password: 'CiOnly-12345' },
  });
  if (!setup.ok()) throw new Error(`owner setup: ${setup.status()} ${await setup.text()}`);

  await page.goto(`${base}/workflow/pricewatch000001`);
  await page.getByText('Write the message').first().waitFor();
  await page.waitForTimeout(1500);
  await shot('0-opened');

  await page.locator('[data-test-id="execute-workflow-button"]').click();
  await page.getByText(/executed successfully/i).first().waitFor({ timeout: 60_000 });
  await page.waitForTimeout(4000); // toast fades
  await page.mouse.click(1300, 780); // empty canvas, so nothing stays selected
  await page.keyboard.press('1'); // zoom to fit
  await page.waitForTimeout(800);
  await shot('workflow-run');

  const node = page.locator('[data-name="Write the message"]').first();
  if (await node.count()) await node.dblclick({ force: true });
  else await page.mouse.dblclick(949, 395); // where the node sits after zoom to fit
  await page.getByText(/output/i).first().waitFor();
  await page.waitForTimeout(1500);
  await shot('code-node');
} catch (error) {
  await shot('error').catch(() => {});
  throw error;
} finally {
  await browser.close();
}
