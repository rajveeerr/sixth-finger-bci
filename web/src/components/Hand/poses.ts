import type { Command } from "../../store";

// Flexion angles in radians per joint (MCP, PIP, DIP); positive curls toward the palm.
export type FingerPose = readonly [number, number, number];

export interface HandPose {
  thumb: FingerPose;
  fingers: readonly FingerPose[]; // index, middle, ring, little
  sixth: FingerPose; // robotic finger on the ulnar side of the wrist cuff
}

const open: FingerPose = [0.08, 0.1, 0.05];
const fist: FingerPose = [1.45, 1.65, 1.05];
const sixthOpen: FingerPose = [0.15, 0.1, 0.05];
// A hook over the edge of the palm, seen in the plane of the screen (not a closed curl).
const sixthFlexed: FingerPose = [0.85, 0.75, 0.5];

export const POSES: Record<Command, HandPose> = {
  IDLE: { thumb: [0.1, 0.1, 0.05], fingers: [open, open, open, open], sixth: sixthOpen },
  // An unmistakable fist, the robotic finger untouched.
  HAND_GRASP: { thumb: [0.75, 0.7, 0.55], fingers: [fist, fist, fist, fist], sixth: sixthOpen },
  // Only the robotic finger curls; the hand stays open.
  SIXTH_FINGER_FLEX: { thumb: [0.1, 0.1, 0.05], fingers: [open, open, open, open], sixth: sixthFlexed },
};
