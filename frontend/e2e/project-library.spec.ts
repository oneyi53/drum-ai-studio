import { expect, test } from "@playwright/test";

function makeWav(): { name: string; mimeType: string; buffer: Buffer } {
  const sampleRate = 8_000;
  const sampleCount = sampleRate;
  const data = Buffer.alloc(sampleCount * 2);
  for (let i = 0; i < sampleCount; i += 1) {
    data.writeInt16LE(Math.round(Math.sin((2 * Math.PI * 440 * i) / sampleRate) * 5000), i * 2);
  }
  const header = Buffer.alloc(44);
  header.write("RIFF", 0);
  header.writeUInt32LE(36 + data.length, 4);
  header.write("WAVE", 8);
  header.write("fmt ", 12);
  header.writeUInt32LE(16, 16);
  header.writeUInt16LE(1, 20);
  header.writeUInt16LE(1, 22);
  header.writeUInt32LE(sampleRate, 24);
  header.writeUInt32LE(sampleRate * 2, 28);
  header.writeUInt16LE(2, 32);
  header.writeUInt16LE(16, 34);
  header.write("data", 36);
  header.writeUInt32LE(data.length, 40);
  return {
    name: "playwright-e2e-tone.wav",
    mimeType: "audio/wav",
    buffer: Buffer.concat([header, data]),
  };
}

test("creates a project, persists annotations, and restores them after reload", async ({ page }) => {
  const audio = makeWav();
  await page.goto("/");

  await page.locator(".dropzone input[type=file]").setInputFiles(audio);
  await page.getByRole("button", { name: "创建项目" }).click();
  await expect(page.getByText(/项目已创建：/)).toBeVisible();

  await page.getByLabel("时间（秒）").fill("0.250");
  await page.getByLabel("鼓件").selectOption("snare");
  await page.getByRole("button", { name: /记录鼓点/ }).click();
  await expect(page.getByText("人工确认事件 · 1")).toBeVisible();
  await expect(page.getByText("已保存到项目服务器 · 1 条参考标注")).toBeVisible();
  await expect(page.getByRole("button", { name: "snare 第3格 已有鼓点" })).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("事件 1 力度").fill("86");
  await expect(page.getByText("已保存到项目服务器 · 1 条参考标注")).toBeVisible();

  await page.reload();
  await expect(page.getByLabel("选择已有项目")).toContainText(audio.name);
  const projectSelect = page.getByLabel("选择已有项目");
  const projectOption = projectSelect.locator("option").filter({ hasText: audio.name });
  const projectId = await projectOption.getAttribute("value");
  expect(projectId).toBeTruthy();
  await projectSelect.selectOption(projectId!);
  await page.getByRole("button", { name: "打开项目" }).click();

  await expect(page.getByText(/已重新打开项目：playwright-e2e-tone\.wav/)).toBeVisible();
  await expect(page.getByText("已连接项目服务器；已载入 1 条参考标注")).toBeVisible();
  await expect(page.getByText("人工确认事件 · 1")).toBeVisible();
  await expect(page.locator(".editable-event-row").filter({ has: page.getByLabel("事件 1 鼓件") })).toContainText("0.250");
  await expect(page.getByLabel("事件 1 力度")).toHaveValue("86");
});
