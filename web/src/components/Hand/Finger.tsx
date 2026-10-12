import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import type { Group, Material } from "three";
import type { FingerPose } from "./poses";
import { dampAll } from "./spring";

const LAMBDA = 10;

/** A capsule that rotates about its base: the mesh is shifted up by half its length. */
export function Phalanx({ length, radius, material }: { length: number; radius: number; material: Material }) {
  return (
    <mesh position-y={length / 2} material={material} castShadow>
      <capsuleGeometry args={[radius, Math.max(length - 2 * radius, 0.01), 6, 14]} />
    </mesh>
  );
}

export interface FingerProps {
  lengths: readonly [number, number, number];
  radius: number;
  target: FingerPose;
  material: Material;
  /** Drawn at each joint (the robotic finger's discs). */
  joint?: (index: number) => React.ReactNode;
}

/**
 * Three phalanges, each a group rotated about x at its base; positive flexion curls toward
 * the palm (−z, away from the viewer). Angles move by a damped spring through refs.
 */
export function Finger({ lengths, radius, target, material, joint }: FingerProps) {
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

  const radii = [radius, radius * 0.92, radius * 0.85];
  return (
    <group ref={j0}>
      {joint?.(0)}
      <Phalanx length={lengths[0]} radius={radii[0]} material={material} />
      <group ref={j1} position-y={lengths[0]}>
        {joint?.(1)}
        <Phalanx length={lengths[1]} radius={radii[1]} material={material} />
        <group ref={j2} position-y={lengths[1]}>
          {joint?.(2)}
          <Phalanx length={lengths[2]} radius={radii[2]} material={material} />
        </group>
      </group>
    </group>
  );
}
