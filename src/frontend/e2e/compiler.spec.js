import { test, expect } from '@playwright/test';

test.describe('Arm Mobile Executor Platform - End-to-End Workspace Suite', () => {
  test('successfully loads the app dashboard and handles live optimization toggles', async ({ page }) => {
    // Navigate to the local Vite web server
    await page.goto('/');

    // Assert the main app title and structural headers are visible on screen
    await expect(page.locator('body')).toContainText('Arm AI');
    await expect(page.locator('body')).toContainText('Federated Data Plane');

    // Assert that the dashboard loads the default Naive Stride Fallback profile first
    await expect(page.locator('body')).toContainText('Naive Scalar');
    await expect(page.locator('body')).toContainText('0% Latency');

    // Locate and click the "Arm KleidiAI" code toggle button
    const optimizedButton = page.getByRole('button', { name: 'Arm KleidiAI' });
    await expect(optimizedButton).toBeVisible();
    await optimizedButton.click();

    // Assert that the UI state updates instantly to reflect the optimized KleidiAI metrics
    await expect(page.locator('body')).toContainText('Arm KleidiAI');
    await expect(page.locator('body')).toContainText('78% TTFT');
  });
});
