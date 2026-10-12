import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import type { Group } from "three";
import { phalanxGeometry, nailGeometry } from "./geometry";
import { CAST, NAIL } from "./materials";
import type { FingerPose } from "./poses";
import { dampAll } from "./spring";

const LAMBDA = 10;

/**
 * Three joints that follow a target pose with a damped spring, rotating each joint group
 * about x (positive flexion curls toward the palm, −z). Renders only while they move.
 */
export function useJoints(target: FingerPose) {
  const j0 = useRef<Group>(null);
  const j1 = useRef<Group>(null);
  const j2 = useRef<Group>(null);
  const angles = useRef([0, 0, 0]);
  const settled = useRef(false); // the first frames bring the joints to their pose
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => {
    settled.current = false;
    invalidate();
  }, [target, invalidate]);

  useFrame((_, dt) => {
    if (settled.current) return;
    settled.current = dampAll(angles.current, target, LAMBDA, Math.min(dt, 0.1));
    [j0, j1, j2].forEach((ref, i) => {
      if (ref.current) ref.current.rotation.x = -angles.current[i];
    });
    if (!settled.current) invalidate();
  });
  return [j0, j1, j2] as const;
}

export interface FingerProps {
  lengths: readonly [number, number, number];
  radius: number;
  target: FingerPose;
  /** The tip ends in a nail (not the thumb's metacarpal chain). */
  nail?: boolean;
}

/** A finger of the cast: three phalanges, each turning about a sphere at its joint. */
export function Finger({ lengths, radius, target, nail = true }: FingerProps) {
  const [j0, j1, j2] = useJoints(target);
  const radii = useMemo(() => [radius, radius * 0.9, radius * 0.82, radius * 0.74], [radius]);
  const shapes = useMemo(
    () => ({
      p: [0, 1, 2].map((i) => phalanxGeometry(lengths[i], radii[i], radii[i + 1], i === 2)),
      nail: nailGeometry(radii[2] * 1.25, lengths[2] * 0.62),
    }),
    [lengths, radii],
  );
  return (
    <group ref={j0}>
      <mesh geometry={shapes.p[0]} material={CAST} />
      <group ref={j1} position-y={lengths[0]}>
        <mesh geometry={shapes.p[1]} material={CAST} />
        <group ref={j2} position-y={lengths[1]}>
          <mesh geometry={shapes.p[2]} material={CAST} />
          {nail && (
            <mesh
              geometry={shapes.nail}
              material={NAIL}
              position={[0, lengths[2] * 0.36, radii[2] * 0.8]}
              rotation-x={-0.08}
            />
          )}
        </group>
      </group>
    </group>
  );
}
