import { Color, MeshPhysicalMaterial, MeshStandardMaterial } from "three";

// One hand on the page, so its materials live here, outside React: the sixth finger's
// light strip is animated by changing its material on each frame.

export const SIXTH_COLOUR = "#e4502b";

/** A matte cast, like an anatomy model: the hand is the reference, not the subject. */
export const CAST = new MeshPhysicalMaterial({
  color: "#e6e1da",
  roughness: 0.8,
  sheen: 0.3,
  sheenRoughness: 0.7,
  sheenColor: new Color("#ffffff"),
});
export const NAIL = new MeshPhysicalMaterial({ color: "#ebe7e1", roughness: 0.45, clearcoat: 0.3, clearcoatRoughness: 0.4 });
export const PLINTH = new MeshStandardMaterial({ color: "#d9dcdc", roughness: 0.75 });
export const ENGRAVE = new MeshStandardMaterial({ color: "#7e878d", roughness: 0.6 });

/** The device: machined aluminium links, black anodised joints, a fabric strap. */
export const ALU = new MeshStandardMaterial({ color: "#cfd4d8", metalness: 0.85, roughness: 0.3 });
export const ANODISED = new MeshStandardMaterial({ color: "#3b4148", metalness: 0.65, roughness: 0.4 });
export const HINGE = new MeshStandardMaterial({ color: "#7d858c", metalness: 0.8, roughness: 0.32 });
export const PIN = new MeshStandardMaterial({ color: "#16191c", metalness: 0.7, roughness: 0.28 });
export const RUBBER = new MeshStandardMaterial({ color: "#2b2f34", roughness: 0.9 });
export const STRAP = new MeshStandardMaterial({ color: "#30363c", roughness: 0.95 });
export const STITCH = new MeshStandardMaterial({ color: "#9aa2a8", roughness: 0.8 });

/** The one lit part: a light strip along the robotic finger, off until it is commanded. */
const STRIP_OFF = new Color("#d4d8db");
const STRIP_ON = new Color(SIXTH_COLOUR);
export const STRIP = new MeshStandardMaterial({
  color: STRIP_OFF.clone(),
  roughness: 0.45,
  emissive: STRIP_ON.clone(),
  emissiveIntensity: 0,
});

/** 0 = off, 1 = fully lit. */
export function setStrip(level: number) {
  STRIP.emissiveIntensity = 1.6 * level;
  STRIP.color.copy(STRIP_OFF).lerp(STRIP_ON, level);
}
