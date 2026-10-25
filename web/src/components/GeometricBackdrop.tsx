// Extracted from App.tsx during the P7b module split.

export function GeometricBackdrop() {
  return (
    <div className="geometric-backdrop" aria-hidden="true">
      <span className="arc arc-left" />
      <span className="arc arc-right" />
      <span className="paper-block top-block" />
      <span className="paper-block bottom-block" />
      <span className="line line-one" />
      <span className="line line-two" />
      <span className="square-dot" />
    </div>
  );
}
