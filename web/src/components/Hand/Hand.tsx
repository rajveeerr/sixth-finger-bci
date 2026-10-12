import { ContactShadows, OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useMemo } from "react";
import { MeshStandardMaterial } from "three";
import type { Command } from "../../store";
import { Finger } from "./Finger";
import { POSES } from "./poses";
import { SixthFinger } from "./SixthFinger";

// A right hand seen from the back, sizes in centimetres (01-ARCHITECTURE.md §6).
const FINGERS = [
  { x: -2.75, lengths: [4.0, 2.5, 2.0], radius: 0.82 }, // index
  { x: -0.9, lengths: [4.4, 2.8, 2.1], radius: 0.86 }, // middle
  { x: 0.95, lengths: [4.1, 2.6, 2.0], radius: 0.8 }, // ring
  { x: 2.75, lengths: [3.3, 2.1, 1.8], radius: 0.7 }, // little
] as const;

function HandModel({ command }: { command: Command }) {
  const pose = POSES[command];
  const skin = useMemo(() => new MeshStandardMaterial({ color: "#d9d0c7", roughness: 0.75 }), []);
  const cuff = useMemo(() => new MeshStandardMaterial({ color: "#56616a", metalness: 0.5, roughness: 0.45 }), []);
  return (
    <group position-y={-3.5}>
      {/* wrist and the start of the forearm */}
      <mesh position-y={-2.2} scale={[1.15, 1, 0.62]} material={skin}>
        <cylinderGeometry args={[3.05, 3.2, 4.6, 32]} />
      </mesh>
      {/* palm */}
      <RoundedBox args={[8, 9, 2.2]} radius={0.9} smoothness={4} position-y={4.5} material={skin} />
      {FINGERS.map((f, i) => (
        <group key={i} position={[f.x, 9, 0]}>
          <Finger lengths={f.lengths} radius={f.radius} target={pose.fingers[i]} material={skin} />
        </group>
      ))}
      {/* thumb: base on the radial side, turned 40° outward */}
      <group position={[-3.9, 2.4, 0.3]} rotation={[0, 0.5, 0.7]}>
        <Finger lengths={[4.5, 3.2, 2.6]} radius={1.0} target={pose.thumb} material={skin} />
      </group>
      {/* wrist cuff and the robotic sixth finger on its ulnar side */}
      <mesh position-y={-1.4} scale={[1.18, 1, 0.66]} material={cuff}>
        <cylinderGeometry args={[3.35, 3.35, 1.8, 32]} />
      </mesh>
      {/* Turned a quarter about its own axis, so it curls across the back of the hand, in
          the plane of the screen, and reads from the back of a room. */}
      <group position={[5.2, -0.8, 1.8]} rotation-z={-0.12}>
        <group rotation-y={Math.PI / 2}>
          <SixthFinger pose={pose.sixth} active={command === "SIXTH_FINGER_FLEX"} />
        </group>
      </group>
    </group>
  );
}

/** The 3D hand; renders only while something moves (frameloop "demand"). */
export function Hand({ command }: { command: Command }) {
  return (
    <div className="hand" data-testid="hand" data-command={command}>
      <Canvas frameloop="demand" dpr={[1, 2]} camera={{ position: [18, 9, 42], fov: 32 }} shadows={false}>
        <ambientLight intensity={0.75} />
        <directionalLight position={[6, 12, 10]} intensity={1.5} />
        <directionalLight position={[-8, 4, -6]} intensity={0.45} />
        <HandModel command={command} />
        <ContactShadows position={[0, -8.2, 0]} opacity={0.28} scale={26} blur={2.6} far={6} frames={1} />
        <OrbitControls
          target={[0, 3.6, 0]}
          enablePan={false}
          enableZoom={false}
          minAzimuthAngle={-0.7}
          maxAzimuthAngle={0.9}
          minPolarAngle={1.05}
          maxPolarAngle={1.75}
        />
      </Canvas>
    </div>
  );
}
