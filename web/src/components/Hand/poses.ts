import type { Command } from "../../store";

// Flexion angles in radians per joint (MCP, PIP, DIP), thumb first. Tuned in P11.
export type FingerPose = [number, number, number];

export interface HandPose {
  fingers: FingerPose[]; // thumb, index, middle, ring, little
  sixth: FingerPose; // robotic finger on the ulnar side of the wrist
}

const open: FingerPose = [0.1, 0.1, 0.05];
const fist: FingerPose = [1.4, 1.6, 1.0];

export const POSES: Record<Command, HandPose> = {
  IDLE: { fingers: [open, open, open, open, open], sixth: [0.1, 0.1, 0.1] },
  HAND_GRASP: { fingers: [[0.9, 0.8, 0.6], fist, fist, fist, fist], sixth: [0.1, 0.1, 0.1] },
  SIXTH_FINGER_FLEX: { fingers: [open, open, open, open, open], sixth: [1.2, 1.3, 1.1] },
};
