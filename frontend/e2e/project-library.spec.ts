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
  await page.getByRole("button", { name: "kick 第3格 空" }).click();
  await expect(page.getByText("人工确认事件 · 2")).toBeVisible();
  await expect(page.getByText("已保存到项目服务器 · 2 条参考标注")).toBeVisible();
  const musicXmlDownloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "导出 MusicXML" }).click();
  const musicXmlDownload = await musicXmlDownloadPromise;
  await musicXmlDownload.saveAs("test-results/drumai-transcription.musicxml");
  const musicXml = await musicXmlDownload.createReadStream();
  const musicXmlChunks: Buffer[] = [];
  for await (const chunk of musicXml) musicXmlChunks.push(Buffer.from(chunk));
  const musicXmlText = Buffer.concat(musicXmlChunks).toString("utf8");
  expect(musicXmlText).toContain("<score-partwise version=\"4.0\">");
  expect(musicXmlText).toContain("<midi-unpitched>38</midi-unpitched>");
  expect(musicXmlText).toContain("<midi-unpitched>36</midi-unpitched>");
  expect(musicXmlText).toContain("<midi-channel>10</midi-channel>");
  expect(musicXmlText).toContain("<per-minute>120</per-minute>");
  expect(musicXmlText).toContain("<display-step>C</display-step>");
  const parsedMusicXml = await page.evaluate((xml) => {
    const document = new DOMParser().parseFromString(xml, "application/xml");
    const notes = Array.from(document.getElementsByTagName("note"));
    const unpitchedNotes = notes.filter((note) => note.getElementsByTagName("unpitched").length > 0);
    return {
      parserErrors: document.getElementsByTagName("parsererror").length,
      noteCount: notes.length,
      chordCount: document.getElementsByTagName("chord").length,
      drumChannels: Array.from(document.getElementsByTagName("midi-instrument")).map((item) =>
        item.getElementsByTagName("midi-channel")[0]?.textContent),
      instrumentAfterDuration: unpitchedNotes.every((note) => {
        const children = Array.from(note.children).map((child) => child.tagName);
        return children.indexOf("duration") >= 0 &&
          children.indexOf("instrument") > children.indexOf("duration");
      }),
    };
  }, musicXmlText);
  expect(parsedMusicXml.parserErrors).toBe(0);
  expect(parsedMusicXml.chordCount).toBe(1);
  expect(parsedMusicXml.drumChannels.every((channel) => channel === "10")).toBe(true);
  expect(parsedMusicXml.instrumentAfterDuration).toBe(true);

  await page.reload();
  await expect(page.getByLabel("选择已有项目")).toContainText(audio.name);
  const projectSelect = page.getByLabel("选择已有项目");
  const projectOption = projectSelect.locator("option").filter({ hasText: audio.name });
  const projectId = await projectOption.getAttribute("value");
  expect(projectId).toBeTruthy();
  await projectSelect.selectOption(projectId!);
  await page.getByRole("button", { name: "打开项目" }).click();

  await expect(page.getByText(/已重新打开项目：playwright-e2e-tone\.wav/)).toBeVisible();
  // The connection message is transient and is immediately replaced by the save status.
  // The restored event count and field values below are the durable persistence assertions.
  await expect(page.getByText("人工确认事件 · 2")).toBeVisible();
  await expect(page.getByLabel("事件 1 时间")).toHaveValue("0.25");
  await expect(page.getByLabel("事件 1 力度")).toHaveValue("86");
});
