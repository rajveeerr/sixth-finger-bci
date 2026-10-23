/** The one key for every drawing that tells built from needed: solid is built, dashed is not. */
export function BuiltKey() {
  return (
    <ul className="built-key" aria-label="Key">
      <li data-built="">Built in this project</li>
      <li>Needed in a real system</li>
    </ul>
  );
}
