/** Loading placeholder: a quiet opacity-pulse block, no bounce/scale.
 *  Used while insights/changes/competitors are being fetched. */
export function Skeleton({
  className = "",
  style,
}: {
  className?: string;
  style?: React.CSSProperties;
}) {
  return <div aria-hidden="true" className={`skeleton ${className}`} style={style} />;
}
