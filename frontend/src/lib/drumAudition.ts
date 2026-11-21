/**
 * Dependency-free WebAudio drum audition.
 *
 * AudioContext is created by the UI only after the user enables audition
 * and interacts with a note, so browsers never prompt or allocate audio
 * resources by default.
 */

export type DrumVoice = "kick" | "snare" | "hat" | "tom" | "crash";

export function drumVoiceForInstrument(instrument: string): DrumVoice {
  if (instrument === "kick") return "kick";
  if (instrument === "snare") return "snare";
  if (instrument.includes("hihat")) return "hat";
  if (instrument.includes("tom")) return "tom";
  if (instrument === "crash" || instrument === "ride") return "crash";
  return "snare";
}

export function normalizedAuditionVelocity(velocity: number): number {
  return Math.max(1, Math.min(127, Math.round(velocity))) / 127;
}

function envelope(context: AudioContext, duration: number, level: number): GainNode {
  const gain = context.createGain();
  gain.gain.setValueAtTime(0, context.currentTime);
  gain.gain.linearRampToValueAtTime(level, context.currentTime + 0.004);
  gain.gain.exponentialRampToValueAtTime(0.001, context.currentTime + duration);
  gain.connect(context.destination);
  return gain;
}

function tone(
  context: AudioContext,
  destination: AudioNode,
  startFrequency: number,
  endFrequency: number,
  duration: number,
  type: OscillatorType = "sine",
): void {
  const oscillator = context.createOscillator();
  oscillator.type = type;
  oscillator.frequency.setValueAtTime(startFrequency, context.currentTime);
  oscillator.frequency.exponentialRampToValueAtTime(endFrequency, context.currentTime + duration);
  oscillator.connect(destination);
  oscillator.start();
  oscillator.stop(context.currentTime + duration + 0.01);
}

function noise(
  context: AudioContext,
  destination: AudioNode,
  duration: number,
  highpass: number,
): void {
  const buffer = context.createBuffer(1, Math.ceil(context.sampleRate * duration), context.sampleRate);
  const channel = buffer.getChannelData(0);
  for (let i = 0; i < channel.length; i += 1) channel[i] = Math.random() * 2 - 1;
  const source = context.createBufferSource();
  const filter = context.createBiquadFilter();
  filter.type = "highpass";
  filter.frequency.setValueAtTime(highpass, context.currentTime);
  source.buffer = buffer;
  source.connect(filter);
  filter.connect(destination);
  source.start();
  source.stop(context.currentTime + duration);
}

/** Schedule one short synthesized hit. No samples, downloads or libraries. */
export function playDrumHit(
  context: AudioContext,
  instrument: string,
  velocity: number,
): void {
  const level = normalizedAuditionVelocity(velocity) * 0.24;
  const voice = drumVoiceForInstrument(instrument);
  const duration = voice === "crash" ? 0.65 : voice === "hat" ? 0.12 : 0.28;
  const output = envelope(context, duration, level);

  if (voice === "kick") {
    tone(context, output, 145, 42, 0.24);
  } else if (voice === "tom") {
    tone(context, output, 190, 75, 0.24, "sine");
  } else if (voice === "snare") {
    tone(context, output, 185, 90, 0.16, "triangle");
    const noiseGain = envelope(context, 0.16, level * 0.65);
    noise(context, noiseGain, 0.16, 900);
  } else {
    noise(context, output, duration, voice === "crash" ? 2200 : 6500);
  }
}
