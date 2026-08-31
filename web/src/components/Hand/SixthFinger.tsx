import type { ThreeElements } from "@react-three/fiber";
import type { FingerPose } from "./poses";

type GroupProps = ThreeElements["group"];

export function SixthFinger({ pose, ...props }: { pose: FingerPose } & GroupProps) {
  return <group userData={{ pose }} {...props} />;
}
