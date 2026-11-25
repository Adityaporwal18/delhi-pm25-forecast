import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Category } from "./api";
import { type ChartRow, axisTicks, tickLabel } from "./chart";
import { TOKENS } from "./tokens";

function hoursLabel(hours: number): string {
  return hours === 0 ? "now" : `+${hours} h`;
}

function valueLabel(value: unknown): string {
  return Array.isArray(value) ? `${String(value[0])}–${String(value[1])} µg/m³` : `${String(value)} µg/m³`;
}

/** Faint CPCB bands behind the lines, so the chart reads in the same colours as the map. */
function categoryBands(categories: readonly Category[], top: number) {
  return categories.map((category, index) => {
    const lower = index === 0 ? 0 : (categories[index - 1]?.upper_ug_m3 ?? 0);
    const upper = Math.min(category.upper_ug_m3 ?? top, top);
    return lower < top ? (
      <ReferenceArea key={category.label} y1={lower} y2={upper} fill={category.colour} fillOpacity={0.12} ifOverflow="hidden" />
    ) : null;
  });
}

interface Props {
  rows: readonly ChartRow[];
  categories: readonly Category[];
  /** The hour the map shows, marked with a dashed line so the chart follows the map while it plays. */
  hour: number;
}

export function ForecastChart({ rows, categories, hour }: Props) {
  const highest = Math.max(100, ...rows.flatMap((row) => [row.band?.[1] ?? 0, row.measured ?? 0, row.median ?? 0]));
  const top = Math.ceil((highest * 1.1) / 50) * 50;
  return (
    <ResponsiveContainer width="100%" height={210}>
      <ComposedChart data={[...rows]} margin={{ top: 8, right: 12, bottom: 18, left: 0 }}>
        {categoryBands(categories, top)}
        <CartesianGrid stroke={TOKENS.rule} strokeDasharray="3 3" />
        <XAxis
          dataKey="horizon"
          type="number"
          domain={[0, 48]}
          ticks={axisTicks(rows)}
          interval={0}
          tickFormatter={tickLabel}
          label={{ value: "hours ahead", position: "insideBottom", offset: -14, fill: TOKENS.ink3, fontSize: 12 }}
          stroke={TOKENS.ink3}
          fontSize={12}
        />
        <YAxis domain={[0, top]} stroke={TOKENS.ink3} fontSize={12} width={44} />
        <ReferenceLine x={hour} stroke={TOKENS.accent} strokeWidth={1.5} strokeDasharray="4 3" />
        <Tooltip
          labelFormatter={(label) => hoursLabel(Number(label))}
          formatter={(value) => valueLabel(value)}
          contentStyle={{ background: TOKENS.paperHi, border: `1px solid ${TOKENS.ink}`, borderRadius: 0 }}
          labelStyle={{ color: TOKENS.ink }}
        />
        <Area dataKey="band" name="80% band" stroke="none" fill={TOKENS.band} isAnimationActive={false} connectNulls />
        <Line dataKey="median" name="Forecast (median)" stroke={TOKENS.ink} strokeWidth={2.5} dot={{ r: 3, fill: TOKENS.ink }} isAnimationActive={false} connectNulls />
        <Line dataKey="measured" name="Measured" stroke="none" dot={{ r: 4, fill: TOKENS.paperHi, stroke: TOKENS.ink, strokeWidth: 1.5 }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
