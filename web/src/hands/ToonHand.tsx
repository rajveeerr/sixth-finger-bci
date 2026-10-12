import { OrbitControls, Outlines, RoundedBox } from "@react-three/drei";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { useEffect, useMemo, useRef } from "react";
import {
  BoxGeometry,
  CapsuleGeometry,
  Color,
  DataTexture,
  Mesh,
  MeshBasicMaterial,
  MeshToonMaterial,
  NearestFilter,
  NoToneMapping,
  OrthographicCamera,
  Quaternion,
  RedFormat,
  SphereGeometry,
  Vector3,
} from "three";
import { mergeGeometries } from "three/examples/jsm/utils/BufferGeometryUtils.js";
import { POSES } from "../components/Hand/poses";
import { damp } from "../components/Hand/spring";
import type { Command } from "../store";
import { HOUSING, PALM, pieces, STRAP, WRIST, type P3, type Piece } from "./rig";

// Option B: the same hand model in 3D, drawn like the bench: four flat tones, an ink
// outline round every part, paper white, and the robotic finger's strip the only colour.

const INK = "#1f272e";
const OUTLINE = 2.4; // device pixels (drei measures outlines in pixels unless screenspace)
const AZ = (55 * Math.PI) / 180;
const EL = (30 * Math.PI) / 180;

/** Four flat tones, like the drawing's shading. */
const TONES = (() => {
  const t = new DataTexture(new Uint8Array([118, 182, 224, 255]), 4, 1, RedFormat);
  t.minFilter = NearestFilter;
  t.magFilter = NearestFilter;
  t.generateMipmaps = false;
  t.needsUpdate = true;
  return t;
})();
const PAPER = new MeshToonMaterial({ color: "#ffffff", gradientMap: TONES });
const STRAP_MAT = new MeshToonMaterial({ color: "#d9dddf", gradientMap: TONES });
const PIN = new MeshBasicMaterial({ color: INK });
const STRIP = new MeshBasicMaterial({ color: "#d4d8da" });
const STRIP_OFF = new Color("#d4d8da");
const STRIP_ON = new Color("#e4502b");

/** Rig coordinates (z up) to three's (y up), mirrored the way the isometric drawing is, so
 * both options show a right hand from the back with the thumb on the left. */
const v3 = (p: P3) => new Vector3(p[0], p[2], p[1]);
const UP = new Vector3(0, 1, 0);

function Plinth() {
  const ticks = useMemo(
    () =>
      mergeGeometries(
        Array.from({ length: 60 }, (_, i) => {
          const major = i % 5 === 0;
          const len = major ? 0.9 : 0.45;
          const g = new BoxGeometry(0.06, 0.02, len);
          g.translate(0, 0.66, 6.3 - len / 2);
          g.rotateY((i / 60) * Math.PI * 2);
          return g;
        }),
      ),
    [],
  );
  return (
    <group position-y={-8.95}>
      <mesh material={PAPER}>
        <cylinderGeometry args={[6.8, 6.8, 1.3, 64]} />
        <Outlines thickness={OUTLINE} color={INK} />
      </mesh>
      <mesh geometry={ticks} material={PIN} />
    </group>
  );
}

function Body() {
  return (
    <>
      <Plinth />
      <mesh material={PAPER} position-y={-3.6} scale={[WRIST.rx, 1, WRIST.ry]}>
        <cylinderGeometry args={[1, 1, 8.4, 48]} />
        <Outlines thickness={OUTLINE} color={INK} />
      </mesh>
      <mesh material={STRAP_MAT} position-y={STRAP.z0 + STRAP.h / 2} scale={[WRIST.rx + STRAP.grow, 1, WRIST.ry + STRAP.grow]}>
        <cylinderGeometry args={[1, 1, STRAP.h, 48]} />
        <Outlines thickness={OUTLINE} color={INK} />
      </mesh>
      <RoundedBox args={[PALM.w, PALM.h, PALM.d]} radius={0.9} smoothness={5} position-y={PALM.h / 2} material={PAPER}>
        <Outlines thickness={OUTLINE} color={INK} />
      </RoundedBox>
      <RoundedBox
        args={[HOUSING.w, HOUSING.h, HOUSING.d]}
        radius={0.3}
        smoothness={3}
        position={[HOUSING.x + HOUSING.w / 2, HOUSING.z0 + HOUSING.h / 2, HOUSING.y + HOUSING.d / 2]}
        material={PAPER}
      >
        <Outlines thickness={OUTLINE} color={INK} />
      </RoundedBox>
    </>
  );
}

type Pose = (typeof POSES)[Command];
const flat = (p: Pose) => [...p.thumb, ...p.fingers.flat(), ...p.sixth];
function unflat(v: number[]): Pose {
  return {
    thumb: [v[0], v[1], v[2]],
    fingers: [0, 1, 2, 3].map((i) => [v[3 + i * 3], v[4 + i * 3], v[5 + i * 3]] as const),
    sixth: [v[15], v[16], v[17]],
  };
}

/** The moving pieces: one mesh per segment, knuckle and link, placed from the rig. */
function Moving({ command }: { command: Command }) {
  const layout = useMemo(() => pieces(POSES.IDLE), []);
  const shapes = useMemo(
    () =>
      Object.fromEntries(
        layout.map((p) => {
          if (p.kind === "ball") return [p.part, new SphereGeometry(p.r, 24, 16)];
          const len = Math.hypot(p.b[0] - p.a[0], p.b[1] - p.a[1], p.b[2] - p.a[2]);
          return [p.part, new CapsuleGeometry(p.r, len, 8, 20)];
        }),
      ),
    [layout],
  );
  const meshes = useRef<Record<string, Mesh | null>>({});
  const current = useRef(flat(POSES[command]));
  const settled = useRef(false);
  const invalidate = useThree((s) => s.invalidate);
  const lit = command === "SIXTH_FINGER_FLEX";

  useEffect(() => {
    settled.current = false;
    invalidate();
  }, [command, invalidate]);

  useFrame((_, dt) => {
    if (settled.current) return;
    const goal = flat(POSES[command]);
    const cur = current.current;
    let moving = false;
    for (let i = 0; i < cur.length; i++) {
      cur[i] = damp(cur[i], goal[i], 10, Math.min(dt, 0.1));
      if (Math.abs(cur[i] - goal[i]) > 1e-3) moving = true;
    }
    STRIP.color.lerp(lit ? STRIP_ON : STRIP_OFF, 0.25);
    if (!STRIP.color.equals(lit ? STRIP_ON : STRIP_OFF)) moving = true;
    const q = new Quaternion();
    for (const p of pieces(unflat(cur))) {
      const m = meshes.current[p.part];
      if (!m) continue;
      if (p.kind === "ball") {
        m.position.copy(v3(p.c));
      } else {
        const a = v3(p.a);
        const b = v3(p.b);
        m.position.copy(a).add(b).multiplyScalar(0.5);
        m.quaternion.copy(q.setFromUnitVectors(UP, b.sub(a).normalize()));
      }
    }
    settled.current = !moving;
    if (moving) invalidate();
  });

  return (
    <>
      {layout.map((p: Piece) => {
        const ref = (m: Mesh | null) => {
          meshes.current[p.part] = m;
        };
        if (p.kind === "ball") {
          return (
            <mesh key={p.part} ref={ref} material={PAPER} geometry={shapes[p.part]}>
              <Outlines thickness={OUTLINE} color={INK} />
            </mesh>
          );
        }
        const len = Math.hypot(p.b[0] - p.a[0], p.b[1] - p.a[1], p.b[2] - p.a[2]);
        return (
          <mesh key={p.part} ref={ref} material={PAPER} geometry={shapes[p.part]}>
            <Outlines thickness={OUTLINE} color={INK} />
            {p.kind === "link" && (
              <>
                <mesh material={STRIP} position={[0, 0, p.r * 0.95]}>
                  <boxGeometry args={[p.r * 0.55, len * 0.55, 0.08]} />
                </mesh>
                <mesh material={PIN} position-y={-len / 2} rotation-z={Math.PI / 2}>
                  <cylinderGeometry args={[p.r * 0.38, p.r * 0.38, p.r * 2.25, 16]} />
                </mesh>
                {p.part === "x2" && (
                  <mesh material={PIN} position-y={len / 2 + p.r * 0.2}>
                    <sphereGeometry args={[p.r * 1.02, 20, 14]} />
                  </mesh>
                )}
              </>
            )}
          </mesh>
        );
      })}
    </>
  );
}

/** Keeps the whole model in view at any canvas size (orthographic zoom). */
function Framing() {
  const width = useThree((s) => s.size.width);
  const height = useThree((s) => s.size.height);
  const get = useThree((s) => s.get);
  useEffect(() => {
    const { camera, invalidate } = get();
    if (!(camera instanceof OrthographicCamera) || !width) return;
    camera.zoom = Math.min(height / 31, width / 24);
    camera.updateProjectionMatrix();
    invalidate();
  }, [width, height, get]);
  return null;
}

/** Option B: the hand model in 3D, drawn like the bench. */
export function ToonHand({ command }: { command: Command }) {
  const d = 60;
  return (
    <div className="hand" data-command={command}>
      <Canvas
        orthographic
        frameloop="demand"
        dpr={[1, 2]}
        gl={{ toneMapping: NoToneMapping }}
        camera={{ position: [d * Math.cos(EL) * Math.cos(AZ), 4.6 + d * Math.sin(EL), d * Math.cos(EL) * Math.sin(AZ)], zoom: 16 }}
      >
        <ambientLight intensity={0.9} />
        <directionalLight position={[-Math.sin(AZ) * 10, 12, Math.cos(AZ) * 10]} intensity={1.6} />
        <Body />
        <Moving command={command} />
        <Framing />
        <OrbitControls target={[0.5, 4.6, 0]} enablePan={false} enableZoom={false} minPolarAngle={0.7} maxPolarAngle={1.7} />
      </Canvas>
    </div>
  );
}
