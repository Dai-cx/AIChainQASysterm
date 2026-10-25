// Extracted from App.tsx during the P7b module split.

export function JsonBlock(props: { value: unknown; title?: string }) {
  return (
    <div className="json-block">
      {props.title && <h4>{props.title}</h4>}
      <pre>{JSON.stringify(props.value ?? {}, null, 2)}</pre>
    </div>
  );
}
