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
          <b>EEGNet</b> A small neural network designed for EEG (Lawhern et al., Journal of Neural Engineering, 2018).
          It learns which sensors and which rhythms tell the choices apart.
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
