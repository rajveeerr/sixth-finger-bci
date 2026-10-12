// A critically damped step toward a target: frame-rate independent, settles in ≈ 0.3–0.5 s
// at lambda ≈ 10 (01-ARCHITECTURE.md §6).
export function damp(current: number, target: number, lambda: number, dt: number): number {
  return target + (current - target) * Math.exp(-lambda * dt);
}

/** Damp every joint in place; true once all are within `epsilon` of their targets. */
export function dampAll(current: number[], target: readonly number[], lambda: number, dt: number, epsilon = 1e-3): boolean {
  let settled = true;
  for (let i = 0; i < current.length; i++) {
    current[i] = damp(current[i], target[i], lambda, dt);
    if (Math.abs(current[i] - target[i]) > epsilon) settled = false;
  }
  return settled;
}
