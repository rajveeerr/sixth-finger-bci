import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { Color, MeshStandardMaterial } from "three";
import { Finger } from "./Finger";
import type { FingerPose } from "./poses";
import { damp } from "./spring";

export const SIXTH_COLOUR = "#e4502b";
const LENGTHS = [3.5, 3.0, 2.5] as const; // 01-ARCHITECTURE.md §6
const RADIUS = 0.62;

/**
 * The robotic finger: brushed metal segments with visible joint discs, glowing in the
 * sixth-finger colour while it is commanded, so it reads from the back of a room.
 */
// One robotic finger on the page: its materials live here, outside React, because the
// glow is animated by changing the material on each frame.
const METAL = new MeshStandardMaterial({
  color: "#c3cad0", // brushed steel; strongly metallic surfaces look black without an environment map
  metalness: 0.45,
  roughness: 0.35,
  emissive: new Color(SIXTH_COLOUR),
  emissiveIntensity: 0,
});
const DISC = new MeshStandardMaterial({ color: "#3b454d", metalness: 0.6, roughness: 0.4 });

function setGlow(value: number) {
  METAL.emissiveIntensity = value;
}

export function SixthFinger({ pose, active }: { pose: FingerPose; active: boolean }) {
  const glow = useRef(0);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => invalidate(), [active, invalidate]);
  useFrame((_, dt) => {
    const target = active ? 0.6 : 0;
    glow.current = damp(glow.current, target, 8, Math.min(dt, 0.1));
    setGlow(glow.current);
    if (Math.abs(glow.current - target) > 1e-3) invalidate();
  });

  return (
    <Finger
      lengths={LENGTHS}
      radius={RADIUS}
      target={pose}
      material={METAL}
      joint={(i) => (
        <mesh rotation-z={Math.PI / 2} material={DISC}>
          <cylinderGeometry args={[RADIUS * (1.25 - i * 0.08), RADIUS * (1.25 - i * 0.08), RADIUS * 1.5, 20]} />
        </mesh>
      )}
    />
  );
}
