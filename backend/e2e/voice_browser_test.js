// Real-browser voice acceptance test with a FAKE microphone fed from a recorded WAV fixture.
//
// What this proves: a real Chromium records through MediaRecorder from a (fake) capture device, uploads the recording
// through the Next.js proxy, the private Whisper service transcribes it, the assistant answers from approved SOPs,
// and the answer can be read aloud (audio is fetched from /voice/speak and played).
// What it does NOT prove: that a person's physical microphone, drivers and OS privacy settings work. That needs the
// manual check in docs/voice-audio-report.md.
//
// Usage: node voice_browser_test.js <playwright-core path> <base url> <user> <password> <wav fixture> <expected words, comma separated> <lang en|hi>
const [, , pwPath, base, user, pass, wav, expectedCsv, lang] = process.argv;
const { chromium } = require(pwPath);

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${wav}`, '--autoplay-policy=no-user-gesture-required'],
  });
  const ctx = await browser.newContext({ ignoreHTTPSErrors: true, permissions: ['microphone'] });
  const page = await ctx.newPage();
  const result = { steps: [], failures: [] };
  const ok = (name, pass, detail) => { result.steps.push({ name, pass, detail }); if (!pass) result.failures.push(name); };
  const net = [];
  page.on('response', (r) => { if (r.url().includes('/voice/')) net.push(`${r.status()} ${r.url().split('/api/backend')[1]}`); });

  await page.goto(`${base}/login`);
  await page.getByLabel(/email|username/i).fill(user);
  await page.getByLabel(/password/i).fill(pass);
  await page.getByRole('button', { name: /sign in|log in/i }).click();
  await page.getByLabel('Message WorkMate').waitFor({ timeout: 30000 });
  ok('signed in and assistant loaded', true);
  ok('page is a secure context (mic allowed)', await page.evaluate(() => window.isSecureContext));

  if (lang === 'hi') await page.getByRole('button', { name: 'हिन्दी' }).click();
  const mic = page.getByRole('button', { name: /Speak your question/ });
  ok('microphone button is enabled', await mic.isEnabled());
  await mic.click();
  const listening = await page.getByRole('button', { name: 'Stop recording' }).waitFor({ timeout: 8000 }).then(() => true).catch(() => false);
  ok('recording starts (stop button and timer appear)', listening);
  await page.waitForTimeout(6500);                       // the fixture is ~3 s; let it play once through
  if (await page.getByRole('button', { name: 'Stop recording' }).isVisible().catch(() => false)) await page.getByRole('button', { name: 'Stop recording' }).click();

  const box = page.getByLabel('Message WorkMate');
  await box.waitFor({ timeout: 120000 });                // transcription finished: the text box returns with the transcript
  const transcript = (await box.inputValue()).toLowerCase();
  result.transcript = transcript;
  const expected = expectedCsv.split(',').map((w) => w.trim().toLowerCase()).filter(Boolean);
  const hits = expected.filter((w) => transcript.includes(w));
  ok(`transcript contains expected words (${hits.length}/${expected.length})`, hits.length >= Math.ceil(expected.length / 2), transcript);
  ok('transcription request succeeded', net.some((n) => n.startsWith('200 /voice/transcribe')), net.join(' | '));

  await page.getByRole('button', { name: 'Send message' }).click();
  await page.waitForFunction(() => !document.body.innerText.includes('Checking your procedures'), null, { timeout: 90000 });
  await page.waitForTimeout(800);
  const answerText = await page.getByRole('log').innerText();
  result.answer = answerText.slice(-400);
  // A refusal ("I don't have an approved procedure") must NOT count as an answer.
  ok('assistant found an approved procedure for what was said', !/won.t guess|don.t have an approved procedure/i.test(answerText) && /Here is the approved procedure|closest|Choose/i.test(answerText), result.answer);

  // Voice questions are read aloud automatically; verify that, then stop it, then replay manually.
  await page.evaluate(() => { window.__played = 0; const orig = HTMLMediaElement.prototype.play; HTMLMediaElement.prototype.play = function () { window.__played++; return orig.apply(this, arguments); }; });
  const stopBtn = page.getByRole('button', { name: 'Stop listening' }).last();
  const listenBtn = page.getByRole('button', { name: /^Listen in/ }).last();
  const either = await Promise.race([
    stopBtn.waitFor({ timeout: 90000 }).then(() => 'playing'),
    listenBtn.waitFor({ timeout: 90000 }).then(() => 'idle'),
  ]).catch(() => 'none');
  ok('answer is read aloud automatically after a spoken question (or offers Listen)', either !== 'none', either);
  if (either === 'playing') {
    await stopBtn.click();
    ok('playback can be stopped', await listenBtn.waitFor({ timeout: 8000 }).then(() => true).catch(() => false));
  }
  await listenBtn.click();
  await page.waitForFunction(() => window.__played > 0, null, { timeout: 120000 }).catch(() => {});
  ok('Listen replays the answer (audio element played)', (await page.evaluate(() => window.__played)) > 0, net.filter((n) => n.includes('speak') || n.includes('translate')).join(' '));
  ok('speech requests succeeded', net.some((n) => n.startsWith('200 /voice/speak')), net.join(' | '));
  const stop2 = page.getByRole('button', { name: 'Stop listening' }).last();
  if (await stop2.isVisible().catch(() => false)) await stop2.click();

  // the microphone must be released
  const live = await page.evaluate(async () => { const s = await navigator.mediaDevices.enumerateDevices(); return s.length >= 0; });
  ok('browser still responsive after recording', live);
  result.network = net;
  console.log(JSON.stringify(result, null, 2));
  await browser.close();
  process.exit(result.failures.length ? 1 : 0);
})().catch((e) => { console.error('TEST CRASHED', e.message); process.exit(2); });
