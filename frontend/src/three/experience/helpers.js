import * as THREE from "three";

export const SCENES = 11;

export const lerp = THREE.MathUtils.lerp;
export const clamp = THREE.MathUtils.clamp;

export function smoothstep(a, b, x) {
  const t = clamp((x - a) / (b - a || 1e-6), 0, 1);
  return t * t * (3 - 2 * t);
}

// Presence value (0..1) that ramps up after `start`, stays high, ramps down before `end`.
export function band(p, start, end, fade) {
  const a = smoothstep(start, start + fade, p);
  const b = 1 - smoothstep(end - fade, end, p);
  return clamp(Math.min(a, b), 0, 1);
}

// Cinematic camera keyframes — one per scene. Camera travels through one connected world.
export const CAM = [
  { pos: [0.6, 5.2, 23], look: [0, 2.7, 0] },       // 0  Enter command center (wide, low establishing)
  { pos: [0, 2.5, 8.6], look: [0, 2.4, 2.8] },      // 1  The request (dolly toward console)
  { pos: [2.2, 17, 23], look: [0, 0, -13] },        // 2  Market discovery (pull far up + back)
  { pos: [-8.6, 3, 4.2], look: [-5, 1.1, -7] },     // 3  Supplier intelligence (descend into cluster)
  { pos: [3.7, 3, 6.8], look: [0.4, 2, 0] },        // 4  Verification (beside the core)
  { pos: [0, 2.5, 11.4], look: [1.9, 1.6, -0.4] },  // 5  Negotiation (hero framing)
  { pos: [0, 10.6, 18], look: [0, 1, -1.2] },       // 6  Multi-vendor war room (orbital high)
  { pos: [7.9, 3.6, 8], look: [5, 2.3, 1] },        // 7  True landed cost (close detail)
  { pos: [3.6, 2.7, 10], look: [2.2, 1.4, -1] },    // 8  Recommendation (orbit to hero)
  { pos: [0.6, 2.3, 10], look: [1.5, 1.5, -0.8] },  // 9  Human decision (calm, centered)
  { pos: [0, 4.3, 15.5], look: [0, 1.4, 0] },       // 10 Mission complete (pull back, seal)
];
