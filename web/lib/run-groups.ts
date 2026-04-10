import { NegotiationStep, Phase } from "./api-types";


export type PhaseGroup = {
  phase: Phase;
  steps: NegotiationStep[];
};


export function groupStepsByPhase(
  phases: Phase[],
  steps: NegotiationStep[],
): PhaseGroup[] {
  return phases.map((phase) => ({
    phase,
    steps: steps.filter((step) => step.phase === phase.name),
  }));
}
