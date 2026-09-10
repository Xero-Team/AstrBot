import { expect, test } from '@playwright/test';

const dashboardOrigin = `http://127.0.0.1:${
  process.env.ASTRBOT_E2E_DASHBOARD_PORT ?? '3000'
}`;
const backendOrigin = `http://127.0.0.1:${
  process.env.ASTRBOT_E2E_BACKEND_PORT ?? '6185'
}`;
const dashboardToken = 'plugin-ui-e2e-dashboard-token';
const privateProviderError = 'provider://secret-e2e-token@internal.invalid';
const privatePath = '/tmp/astrbot-e2e/private-provider-trace';

async function authenticateAndReset(page: import('@playwright/test').Page) {
  await page.context().addCookies([
    {
      name: 'astrbot_dashboard_jwt',
      value: dashboardToken,
      domain: '127.0.0.1',
      path: '/api/v1',
      httpOnly: true,
      sameSite: 'Strict',
      secure: false,
    },
  ]);
  await page.addInitScript((token) => {
    localStorage.setItem('token', token);
    localStorage.setItem('user', 'plugin-ui-e2e');
    localStorage.setItem('astrbot-locale', 'en-US');
  }, dashboardToken);

  const response = await page.request.post(
    `${backendOrigin}/api/e2e/knowledge-base/reset`,
    {
      headers: {
        Authorization: `Bearer ${dashboardToken}`,
        Cookie: `astrbot_dashboard_jwt=${dashboardToken}`,
      },
    },
  );
  expect(response.ok()).toBe(true);
}

async function createKnowledgeBase(page: import('@playwright/test').Page) {
  await page.goto(`${dashboardOrigin}/#/knowledge-base`);
  await page
    .getByRole('button', { name: 'Create Knowledge Base' })
    .first()
    .click();
  await page.getByRole('textbox', { name: 'Name' }).fill('E2E Operator Guide');
  await page
    .locator('.v-select')
    .filter({ hasText: 'Embedding Model' })
    .first()
    .click();
  await page.getByRole('option', { name: /Test Embedding/ }).click();
  await page.getByRole('button', { name: 'Create', exact: true }).click();
  await expect(
    page.getByText('Knowledge base created successfully'),
  ).toBeVisible();
  await page.getByText('E2E Operator Guide', { exact: true }).first().click();
  await page.getByRole('tab', { name: /Documents/ }).click();
}

test.describe('knowledge-base operator workflow', () => {
  test.skip(({ browserName }) => browserName !== 'chromium');

  test.beforeEach(async ({ page }) => {
    await authenticateAndReset(page);
  });

  test('completes the knowledge-base lifecycle', async ({ page }) => {
    await createKnowledgeBase(page);
    const taskResponse = () =>
      page.waitForResponse(
        (response) =>
          response.url().includes('/api/v1/knowledge-bases/tasks/') &&
          response.request().method() === 'GET',
      );
    await page.getByRole('button', { name: 'Upload Document' }).click();
    await page
      .locator('input[type="file"]')
      .first()
      .setInputFiles({
        name: 'operator-guide.md',
        mimeType: 'text/markdown',
        buffer: Buffer.from('# Operators\nE2E knowledge-base guide'),
      });
    const processingResponse = taskResponse();
    await page.getByRole('button', { name: 'Upload', exact: true }).click();
    const processingPayload = await (await processingResponse).json();
    expect(processingPayload).toMatchObject({
      status: 'ok',
      data: { status: 'processing' },
    });
    const completedResponse = taskResponse();

    await expect(
      page.getByText('operator-guide.md', { exact: true }),
    ).toBeVisible();
    const completedPayload = await (await completedResponse).json();
    expect(completedPayload).toMatchObject({
      status: 'ok',
      data: { status: 'completed' },
    });
    await expect(page.getByText('Created', { exact: true })).toBeVisible();

    await page.getByRole('button', { name: 'View' }).click();
    await expect(
      page.getByRole('heading', { name: 'operator-guide.md' }),
    ).toBeVisible();
    await expect(
      page.getByText('Operators use the E2E knowledge-base guide.'),
    ).toBeVisible();
    await expect(page.locator('body')).not.toContainText(privatePath);

    await page.getByRole('button', { name: 'Reindex' }).click();
    await expect(
      page.getByText('Document rebuilt with current chunk settings'),
    ).toBeVisible();

    await page.goBack();
    await page.getByRole('tab', { name: /Retrieval/ }).click();
    await page.getByRole('textbox', { name: 'Query' }).fill('Operators');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(
      page.getByText('Search completed, found 1 results'),
    ).toBeVisible();
    await expect(
      page.getByText('Operators use the E2E knowledge-base guide.'),
    ).toBeVisible();

    await page.getByRole('tab', { name: /Documents/ }).click();
    await page.getByRole('button', { name: 'Delete' }).first().click();
    await page.getByRole('button', { name: '删除', exact: true }).click();
    await expect(
      page.getByText('operator-guide.md', { exact: true }),
    ).toHaveCount(0);

    await page.goBack();
    await page.locator('.list-action-icon-btn').last().click({ force: true });
    await page
      .locator('.v-overlay-container')
      .getByRole('button', { name: 'Delete', exact: true })
      .click();
    await expect(page.getByText('No knowledge bases')).toBeVisible();
  });

  test('keeps failed upload diagnostics private', async ({ page }) => {
    await createKnowledgeBase(page);
    await page.getByRole('button', { name: 'Upload Document' }).click();
    await page
      .locator('input[type="file"]')
      .first()
      .setInputFiles({
        name: 'broken-provider.md',
        mimeType: 'text/markdown',
        buffer: Buffer.from('# Broken provider'),
      });
    await page.getByRole('button', { name: 'Upload', exact: true }).click();

    await expect(
      page.getByText('上传失败: Knowledge base task failed'),
    ).toBeVisible();
    await expect(
      page.getByText('broken-provider.md', { exact: true }),
    ).toHaveCount(0);
    await expect(page.locator('body')).not.toContainText(privateProviderError);
    await expect(page.locator('body')).not.toContainText(privatePath);

    await page.getByRole('tab', { name: /Retrieval/ }).click();
    await page.getByRole('textbox', { name: 'Query' }).fill('Broken');
    await page.getByRole('button', { name: 'Search', exact: true }).click();
    await expect(page.getByText('No results found')).toBeVisible();
  });
});
