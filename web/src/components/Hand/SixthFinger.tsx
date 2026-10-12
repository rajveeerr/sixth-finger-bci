import { RoundedBox } from "@react-three/drei";
import { useFrame, useThree } from "@react-three/fiber";
import { useEffect, useRef } from "react";
import { useJoints } from "./Finger";
import { ALU, ANODISED, HINGE, PIN, RUBBER, STRIP, setStrip } from "./materials";
import type { FingerPose } from "./poses";
import { damp } from "./spring";

export const LENGTHS = [3.5, 3.0, 2.5] as const; // 01-ARCHITECTURE.md §6
const WIDTH = 1.2;
const DEPTH = 1.0;
const BARREL = 0.5;

/** A hinge: an anodised barrel across the joint and the steel pin through it. */
function Hinge() {
  return (
    <group rotation-z={Math.PI / 2}>
      <mesh material={HINGE}>
        <cylinderGeometry args={[BARREL, BARREL, WIDTH - 0.32, 24]} />
      </mesh>
      <mesh material={PIN}>
        <cylinderGeometry args={[0.2, 0.2, WIDTH + 0.34, 16]} />
      </mesh>
    </group>
  );
}

/** One machined link from its joint to the next: body, clevis ears, light strip, screws. */
function Link({ length, last }: { length: number; last: boolean }) {
  // The last link has no hinge above it: its body runs on into the fingertip pad.
  const body = length - (last ? BARREL + 0.2 : 2 * BARREL + 0.12);
  const mid = BARREL + 0.06 + body / 2;
  return (
    <>
      <Hinge />
      <RoundedBox args={[WIDTH, body, DEPTH]} radius={0.3} smoothness={4} position-y={mid} material={ALU} />
      {/* the light strip down the back, the one part that lights */}
      <RoundedBox args={[0.34, body * 0.72, 0.06]} radius={0.02} smoothness={2} position={[0, mid, DEPTH / 2]}
        material={STRIP} />
      {/* the tendon channel on the palm side */}
      <mesh position={[0, mid, -DEPTH / 2 - 0.02]} material={ANODISED}>
        <boxGeometry args={[0.26, body * 0.9, 0.06]} />
      </mesh>
      {[-1, 1].map((side) =>
        [0.28, 0.72].map((at) => (
          <mesh key={`${side}${at}`} position={[side * (WIDTH / 2 + 0.01), BARREL + 0.06 + body * at, 0]}
            rotation-z={Math.PI / 2} material={PIN}>
            <cylinderGeometry args={[0.09, 0.09, 0.04, 10]} />
          </mesh>
        )),
      )}
      {!last &&
        [-1, 1].map((side) => (
          <RoundedBox key={side} args={[0.1, 2 * BARREL + 0.3, DEPTH * 0.86]} radius={0.04} smoothness={2}
            position={[side * (WIDTH / 2 - 0.05), length - 0.05, 0]} material={ALU} />
        ))}
      {last && (
        <RoundedBox args={[WIDTH - 0.06, 1.1, DEPTH + 0.06]} radius={0.42} smoothness={4} position-y={length - 0.05}
          material={RUBBER} />
      )}
    </>
  );
}

/**
 * The robotic finger, root joint at the origin, links along +y, flexing toward −z like the
 * hand's own fingers. Its light strip glows in the sixth-finger colour while it is commanded.
 */
export function SixthFinger({ pose, active }: { pose: FingerPose; active: boolean }) {
  const [j0, j1, j2] = useJoints(pose);
  const glow = useRef(0);
  const invalidate = useThree((s) => s.invalidate);

  useEffect(() => invalidate(), [active, invalidate]);
  useFrame((_, dt) => {
    const target = active ? 1 : 0;
    glow.current = damp(glow.current, target, 8, Math.min(dt, 0.1));
    setStrip(glow.current);
    if (Math.abs(glow.current - target) > 1e-3) invalidate();
  });

  return (
    <group ref={j0}>
      <Link length={LENGTHS[0]} last={false} />
      <group ref={j1} position-y={LENGTHS[0]}>
        <Link length={LENGTHS[1]} last={false} />
        <group ref={j2} position-y={LENGTHS[1]}>
          <Link length={LENGTHS[2]} last />
        </group>
      </group>
    </group>
  );
}
