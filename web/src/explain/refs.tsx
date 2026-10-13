import type { ReactNode } from "react";
import { Ref } from "../components/Ref";
import { LINKS } from "./links";

// The references and terms the page uses more than once, each with its hover card.

export function DatasetRef({ children }: { children: ReactNode }) {
  return (
    <Ref
      href={LINKS.paper.url}
      card={
        <>
          <b>The dataset</b> Wang et al., Scientific Data 13, 1109 (2026). 24 stroke patients in Tianjin, China; 40 EEG
          sensors; each patient imagined moving the affected hand or a sixth finger, in three sessions. The paper also
          reports the 85% we checked. The recordings are free to use (CC BY 4.0).
          <span className="ref-link">Opens the paper</span>
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function CueTerm({ children = "cue" }: { children?: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>Cue</b> The instruction on the patient&apos;s screen that says which movement to imagine, and when to
          start. In this study it showed either the hand or the sixth finger.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function TherapyTerm({ children = "two weeks of therapy" }: { children?: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>The therapy</b> Two weeks between the first and second sessions, 8 sessions of about 45 minutes. 14
          patients had BCI therapy: wearing the robotic sixth finger, they imagined moving it, and it moved whenever the
          BCI picked that up. The other 10 had the usual rehabilitation therapy for the same time.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function EegnetRef({ children = "EEGNet" }: { children?: ReactNode }) {
  return (
    <Ref
      href={LINKS.eegnet.url}
      card={
        <>
          <b>EEGNet</b> A small neural network designed for EEG (Lawhern et al., Journal of Neural Engineering, 2018):
          layers of simple sums whose weights are learned from examples. It learns which sensors and which rhythms tell
          the choices apart.
          <span className="ref-link">Opens the paper</span>
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function CspTerm({ children = "CSP with LDA" }: { children?: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>CSP with LDA</b> The standard older method, and the one the dataset&apos;s paper used. CSP (common spatial
          patterns) learns filters that mix the sensors so the two movements differ most; LDA then draws a line between
          them.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function ModelTerm({ children = "model" }: { children?: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>Model</b> A computer program that learned from examples which brain signals go with which instruction.
          Shown new signal, it says which instruction it most likely goes with.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function EegTerm({ children = "EEG" }: { children?: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>EEG</b> Electroencephalography: the tiny voltages the brain makes, millionths of a volt, picked up by
          sensors resting on the scalp. Safe and painless; nothing goes into the head.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function ScoreTerm({ children }: { children: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>How the score is counted</b> How often each choice is read right, averaged over the choices (rest, hand,
          sixth finger), so a model that always says &quot;rest&quot; cannot score well. Guessing scores one in the
          number of choices.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function SureTerm({ children }: { children: ReactNode }) {
  return (
    <Ref
      card={
        <>
          <b>How sure</b> How strongly the model leans to this answer, from its own estimate. It is not how often it is
          right; that is the tally below.
        </>
      }
    >
      {children}
    </Ref>
  );
}

export function PaperRef({ children = "the dataset's paper" }: { children?: ReactNode }) {
  return <DatasetRef>{children}</DatasetRef>;
}
