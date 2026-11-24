/** Whole µg/m³: the 80% band is about ±100 wide, so decimals would claim precision we do not have. */
export function ug(value: number | null): string {
  return value === null ? "?" : String(Math.round(value));
}

interface Props {
  value: number;
  when: string;
  detail: string;
  category: { category: string | null; colour: string | null } | null;
}

/** The station's forecast as the focal point of its panel: the number first, then what it means. */
export function Focal({ value, when, detail, category }: Props) {
  return (
    <div className="focal">
      <p className="focal-line">
        <span className="focal-value">{ug(value)}</span>
        <span className="focal-unit">µg/m³</span>
        {category?.category != null && category.colour != null && (
          <span className="chip">
            <span className="swatch" style={{ background: category.colour }} aria-hidden="true" />
            {category.category}
          </span>
        )}
      </p>
      <p className="focal-when">{when}</p>
      <p className="caption">{detail}</p>
    </div>
  );
}
