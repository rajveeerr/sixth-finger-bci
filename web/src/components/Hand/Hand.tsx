import { ContactShadows, Environment, Lightformer, OrbitControls, RoundedBox } from "@react-three/drei";
import { Canvas, useThree } from "@react-three/fiber";
import { useEffect, useMemo } from "react";
import { BoxGeometry, LatheGeometry, NeutralToneMapping, PerspectiveCamera, Vector2, Vector3 } from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import type { Command } from "../../store";
import { Finger } from "./Finger";
import { forearmGeometry, knuckleY, palmGeometry, sweep } from "./geometry";
import { ANODISED, CAST, ENGRAVE, PIN, PLINTH, STITCH, STRAP } from "./materials";
import { POSES } from "./poses";
import { SixthFinger } from "./SixthFinger";

// A right hand seen from the back, sizes in centimetres (01-ARCHITECTURE.md §6): a matte
// cast on a turned plinth, wearing the robotic sixth finger on a strap at the wrist.
const FINGERS = [
  { x: -2.78, lengths: [4.1, 2.5, 2.0], radius: 0.98, splay: 0.06 }, // index
  { x: -0.9, lengths: [4.5, 2.8, 2.15], radius: 1.0, splay: 0.012 }, // middle
  { x: 0.98, lengths: [4.2, 2.6, 2.0], radius: 0.95, splay: -0.035 }, // ring
  { x: 2.72, lengths: [3.4, 2.15, 1.8], radius: 0.84, splay: -0.1 }, // little
] as const;
const THUMB = [3.7, 3.0, 2.4] as const;

const FOREARM = 8.5;
const WRIST_Y = -7.6; // where the forearm leaves the plinth
const STRAP_Y = -2.0;
const STRAP_H = 2.0;

function Plinth() {
  const shapes = useMemo(() => {
    const base = new LatheGeometry(
      [new Vector2(0, 0), new Vector2(6.6, 0), new Vector2(6.6, 0.55), new Vector2(6.35, 0.8), new Vector2(0, 0.8)],
      72,
    );
    const ticks = mergeGeometries(
      Array.from({ length: 72 }, (_, i) => {
        const major = i % 6 === 0;
        const len = major ? 0.8 : 0.4;
        const g = new BoxGeometry(0.05, 0.02, len);
        g.translate(0, 0.81, 5.95 - len / 2);
        g.rotateY((i / 72) * Math.PI * 2);
        return g;
      }),
    );
    const collar = sweep(0.7, () => ({ halfWidth: 3.85, halfDepth: 2.75, zOffset: -0.1 }), { n: 2.4, cap: 0.18, along: 6 });
    return { base, ticks, collar };
  }, []);
  return (
    <group position-y={WRIST_Y - 0.8}>
      <mesh geometry={shapes.base} material={PLINTH} />
      <mesh geometry={shapes.ticks} material={ENGRAVE} />
      <mesh geometry={shapes.collar} material={PLINTH} position-y={0.8} />
    </group>
  );
}

/** The strap and the housing that carries the finger's motor, on the ulnar side. */
function Strap() {
  const shapes = useMemo(() => {
    const band = (h: number, grow: number) =>
      sweep(h, () => ({ halfWidth: 3.06 + grow, halfDepth: 2.03 + grow, zOffset: -0.1 }), { n: 2.4, cap: Math.min(0.22, h / 2), along: 6 });
    return { band: band(STRAP_H, 0.3), stitch: band(0.05, 0.315) };
  }, []);
  return (
    <group position-y={STRAP_Y}>
      <mesh geometry={shapes.band} material={STRAP} />
      <mesh geometry={shapes.stitch} material={STITCH} position-y={0.28} />
      <mesh geometry={shapes.stitch} material={STITCH} position-y={STRAP_H - 0.33} />
      {/* motor housing, lid and four screws */}
      <RoundedBox args={[1.9, 2.9, 2.3]} radius={0.3} smoothness={4} position={[4.15, 1.15, 0.05]} material={ANODISED} />
      <RoundedBox args={[1.7, 0.22, 2.1]} radius={0.08} smoothness={2} position={[4.15, 2.62, 0.05]} material={PIN} />
      {[-0.7, 0.7].flatMap((dy) =>
        [-0.75, 0.85].map((dz) => (
          <mesh key={`${dy}${dz}`} position={[5.11, 1.15 + dy, 0.05 + dz]} rotation-z={Math.PI / 2} material={PIN}>
            <cylinderGeometry args={[0.12, 0.12, 0.04, 12]} />
          </mesh>
        )),
      )}
    </group>
  );
}

function HandModel({ command }: { command: Command }) {
  const pose = POSES[command];
  const shapes = useMemo(() => ({ palm: palmGeometry(), forearm: forearmGeometry(FOREARM) }), []);
  return (
    <group>
      <Plinth />
      <mesh geometry={shapes.forearm} material={CAST} position-y={WRIST_Y} />
      {/* the end of the ulna, a small bump on the little-finger side of the wrist */}
      <mesh material={CAST} position={[2.75, -0.9, 0.25]} scale={[0.6, 0.75, 0.6]}>
        <sphereGeometry args={[1, 24, 16]} />
      </mesh>
      <mesh geometry={shapes.palm} material={CAST} />
      {/* the thenar eminence, the muscle at the base of the thumb */}
      <mesh material={CAST} position={[-2.45, 2.3, -0.4]} rotation-z={0.5} scale={[1.7, 2.8, 1.3]}>
        <sphereGeometry args={[1, 32, 24]} />
      </mesh>
      {/* the knuckles, which stay on the palm when the fingers close */}
      {FINGERS.map((f) => (
        <mesh key={f.x} material={CAST} position={[f.x, knuckleY(f.x) - 0.75, 0.3]}
          scale={[f.radius * 0.98, f.radius * 1.15, f.radius * 0.78]}>
          <sphereGeometry args={[1, 24, 16]} />
        </mesh>
      ))}
      {FINGERS.map((f) => (
        <group key={f.x} position={[f.x, knuckleY(f.x) - 0.5, 0.12]} rotation-z={f.splay}>
          <Finger lengths={f.lengths} radius={f.radius} target={pose.fingers[FINGERS.indexOf(f)]} />
        </group>
      ))}
      {/* thumb: from the base of the palm, out to the radial side and turned toward the palm */}
      <group position={[-2.75, 1.6, -0.45]} rotation={[0.1, 0.8, 0.58]}>
        <Finger lengths={THUMB} radius={1.16} target={pose.thumb} />
      </group>
      <Strap />
      {/* the robotic finger, rooted on the housing and turned so it flexes toward the palm */}
      <group position={[4.2, STRAP_Y + 3.05, 0.05]} rotation={[0, 0.2, -0.05]}>
        <SixthFinger pose={pose.sixth} active={command === "SIXTH_FINGER_FLEX"} />
      </group>
    </group>
  );
}

// What the camera keeps in view: the open hand on its plinth, with the sixth finger's hook.
const TARGET = new Vector3(0.6, 4.9, 0);
const VIEW_HEIGHT = 27.5;
const VIEW_WIDTH = 21;

/** Moves the camera along its line of sight so the hand fits the canvas at any aspect. */
function Framing() {
  const width = useThree((s) => s.size.width);
  const height = useThree((s) => s.size.height);
  const get = useThree((s) => s.get);
  useEffect(() => {
    const { camera, invalidate } = get();
    if (!(camera instanceof PerspectiveCamera) || !width || !height) return;
    const t = Math.tan((camera.fov * Math.PI) / 360);
    const d = Math.max(VIEW_HEIGHT / 2 / t, VIEW_WIDTH / 2 / (t * (width / height))) * 1.06;
    const dir = camera.position.clone().sub(TARGET).normalize();
    camera.position.copy(TARGET).addScaledVector(dir, d);
    invalidate();
  }, [width, height, get]);
  return null;
}

/** The 3D hand; renders only while something moves (frameloop "demand"). */
export function Hand({ command }: { command: Command }) {
  return (
    <div className="hand" data-testid="hand" data-command={command}>
      <Canvas
        frameloop="demand"
        dpr={[1, 2]}
        camera={{ position: [41, 12, 25], fov: 30 }}
        gl={{ toneMapping: NeutralToneMapping }}
        shadows={false}
      >
        <Environment resolution={256} frames={1}>
          <Lightformer form="rect" intensity={1.6} position={[-6, 10, 12]} scale={[16, 10, 1]} />
          <Lightformer form="rect" intensity={0.8} position={[14, 4, 6]} rotation-y={-Math.PI / 2.5} scale={[12, 10, 1]} />
          <Lightformer form="rect" intensity={0.35} position={[0, -6, 6]} rotation-x={Math.PI / 2} scale={[20, 20, 1]} />
          <Lightformer form="ring" intensity={1.4} position={[4, 14, -10]} scale={6} />
        </Environment>
        <ambientLight intensity={0.1} />
        <directionalLight position={[4, 22, 26]} intensity={2.3} />
        <directionalLight position={[-20, 6, -10]} intensity={0.6} />
        <HandModel command={command} />
        <ContactShadows position={[0, WRIST_Y - 0.82, 0]} opacity={0.35} scale={22} blur={2.4} far={4} frames={1} />
        <Framing />
        <OrbitControls
          target={TARGET}
          enablePan={false}
          enableZoom={false}
          minAzimuthAngle={-0.6}
          maxAzimuthAngle={1.4}
          minPolarAngle={1.0}
          maxPolarAngle={1.72}
        />
      </Canvas>
    </div>
  );
}
