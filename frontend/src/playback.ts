/**
 * Shared playback plumbing for the editor's three time views (roll, staff,
 * waveform): one zoom (px per second, null = fit the width) and one live
 * playhead position.
 *
 * The playhead is a @audio-ui/react `Source`, not React state: the roll's
 * Timeline follows it straight in the DOM (its Playhead moves through a
 * CSS variable), and the staff / waveform read it inside their own
 * requestAnimationFrame loops. Publishing a new time costs no React
 * render anywhere — the 60fps clock lives outside the component tree.
 * The <audio> element is the clock source (see main.tsx); the source is
 * only a mirror of it, never a second clock.
 */
import type { WritableSource } from "@audio-ui/react/source";

/** Live playhead time in seconds, published outside React. */
export type PlayheadSource = WritableSource<number>;

/** Roll / staff / waveform zoom, in px per second. */
export const MIN_ZOOM_PX_PER_S = 1;
export const MAX_ZOOM_PX_PER_S = 240;
/** Multiplicative step for the zoom buttons (matches the roll's old step). */
export const ZOOM_STEP = 1.5;
/** Per-notch factor for Ctrl+wheel zoom (smooth, trackpad-friendly). */
export const WHEEL_ZOOM_RATE = 0.002;

/** Clamp a zoom to the supported range; null (fit width) passes through. */
export function clampZoom(zoom: number | null): number | null {
  if (zoom === null) return null;
  if (!Number.isFinite(zoom)) return null;
  return Math.min(MAX_ZOOM_PX_PER_S, Math.max(MIN_ZOOM_PX_PER_S, zoom));
}

/** px/s that fits `durationSeconds` into `widthPx`. */
export function fitZoom(widthPx: number, durationSeconds: number): number {
  if (widthPx <= 0 || durationSeconds <= 0) return 8;
  return widthPx / durationSeconds;
}

/** One button step in, centred on the current view (null = from fit). */
export function zoomIn(current: number | null, fit: number): number {
  return clampZoom((current ?? fit) * ZOOM_STEP) ?? fit;
}

/** One button step out, centred on the current view (null = from fit). */
export function zoomOut(current: number | null, fit: number): number {
  return clampZoom((current ?? fit) / ZOOM_STEP) ?? fit;
}

/** Smooth multiplicative zoom for a wheel notch (factor > 1 zooms in). */
export function zoomByFactor(
  current: number | null,
  fit: number,
  factor: number,
): number {
  return clampZoom((current ?? fit) * factor) ?? fit;
}

/** Wheel delta (px) to a zoom factor: up zooms in, down zooms out. */
export function wheelZoomFactor(deltaY: number): number {
  return Math.exp(-deltaY * WHEEL_ZOOM_RATE);
}
