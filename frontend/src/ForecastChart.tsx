import { Area, CartesianGrid, ComposedChart, Line, ReferenceArea, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Category } from "./api";
import type { ChartRow } from "./chart";
import { TOKENS } from "./tokens";

const TICKS = [0, 6, 12, 18, 24, 30, 36, 42, 48];

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

export function ForecastChart({ rows, categories }: { rows: readonly ChartRow[]; categories: readonly Category[] }) {
  const highest = Math.max(100, ...rows.flatMap((row) => [row.band?.[1] ?? 0, row.measured ?? 0, row.median ?? 0]));
  const top = Math.ceil((highest * 1.1) / 50) * 50;
  return (
    <ResponsiveContainer width="100%" height={280}>
      <ComposedChart data={[...rows]} margin={{ top: 8, right: 12, bottom: 4, left: 0 }}>
        {categoryBands(categories, top)}
        <CartesianGrid stroke={TOKENS.ink800} strokeDasharray="3 3" />
        <XAxis dataKey="horizon" type="number" domain={[0, 48]} ticks={TICKS} tickFormatter={hoursLabel} stroke={TOKENS.textSubtle} fontSize={12} />
        <YAxis domain={[0, top]} stroke={TOKENS.textSubtle} fontSize={12} width={44} />
        <Tooltip
          labelFormatter={(label) => hoursLabel(Number(label))}
          formatter={(value) => valueLabel(value)}
          contentStyle={{ background: TOKENS.ink850, border: `1px solid ${TOKENS.ink800}`, borderRadius: 8 }}
          labelStyle={{ color: TOKENS.text }}
        />
        <Area dataKey="band" name="80% band" stroke="none" fill={TOKENS.band} isAnimationActive={false} connectNulls />
        <Line dataKey="median" name="Forecast (median)" stroke={TOKENS.violet300} strokeWidth={2.5} dot={{ r: 3, fill: TOKENS.violet300 }} isAnimationActive={false} connectNulls />
        <Line dataKey="measured" name="Measured" stroke="none" dot={{ r: 4, fill: TOKENS.measured }} isAnimationActive={false} />
      </ComposedChart>
    </ResponsiveContainer>
  );
}
