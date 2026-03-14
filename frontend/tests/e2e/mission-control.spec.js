import { expect, test } from "@playwright/test";

const TOKEN = "test-token";

async function login(page) {
  await page.goto("/login");
  await page.getByRole("tab", { name: /Owner Token/i }).click();
  await expect(page.getByPlaceholder(/dashboard token/i)).toBeVisible();
  await page.getByPlaceholder(/dashboard token/i).fill(TOKEN);
  await page.getByRole("button", { name: /使用 Token 进入|Enter with token/i }).click();
  await expect(page).toHaveURL(/\/overview$/);
}

test("overview shows chart-driven operations surface", async ({ page }) => {
  await login(page);
  await expect(page.getByRole("heading", { name: /总览|Overview/ })).toBeVisible();
  await expect(page.getByText(/任务漏斗|Task funnel/)).toBeVisible();
  await expect(page.getByText(/Agent 负载热力图|Agent load heatmap/)).toBeVisible();
  await expect(page.getByText(/24h 活动趋势|24h activity trend/)).toBeVisible();
});

test("english locale applies across delivery and conversation workspaces", async ({ page }) => {
  await login(page);
  await page.getByText("English", { exact: true }).click();

  await page.goto("/tasks");
  await expect(page.getByRole("heading", { name: "Delivery Ops" })).toBeVisible();
  await expect(page.getByText("Create task")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Task" })).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "Current owner" })).toBeVisible();

  await page.goto("/conversations");
  await expect(page.getByText("Conversation list")).toBeVisible();
  await expect(page.getByText("Live transcript")).toBeVisible();
  await expect(page.getByRole("button", { name: "Send message" })).toBeVisible();
});

test("mobile delivery workspace defaults to cards", async ({ browser }) => {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
  });
  const page = await context.newPage();
  await login(page);
  await page.goto("/tasks");
  await expect(page.getByText(/^表格$|^Table$/)).toBeVisible();
  await expect(page.getByText(/^卡片$|^Cards$/)).toBeVisible();
  await expect(page.getByRole("button", { name: /Open task|打开任务/ }).first()).toBeVisible();
  await context.close();
});

test("pwa shell is linked from the login page", async ({ page }) => {
  await page.goto("/login");
  await expect(page.locator('link[rel="manifest"]')).toHaveAttribute("href", "/manifest.webmanifest");
});
