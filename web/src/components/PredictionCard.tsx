import type { Prediction } from "../stream/types";

export function PredictionCard({ prediction, correct, total }: {
  prediction: Prediction | null;
  correct: number;
  total: number;
}) {
  return (
    <section className="panel" data-testid="prediction">
      <h2>Decoded intent</h2>
      <p>{prediction ? `${prediction.label} (${Math.round(prediction.confidence * 100)}%)` : "-"}</p>
      <p>Truth: {prediction?.truth ?? "-"}</p>
      <p>Running accuracy: {total ? `${correct}/${total}` : "-"}</p>
    </section>
  );
}
