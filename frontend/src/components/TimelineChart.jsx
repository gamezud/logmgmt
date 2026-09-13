import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

// A single series (event count over time) needs no legend — the section
// heading already names what's plotted. Mark spec follows the project's
// data-viz guidelines: a 2px line, the series hue at ~10% opacity for the
// area fill, hairline recessive gridlines, and a hover tooltip (Recharts'
// built-in one) rather than a static chart with no interaction.
const SERIES_COLOR = "#2a78d6";
const GRIDLINE_COLOR = "#e1e0d9";
const MUTED_INK = "#898781";

export default function TimelineChart({ data }) {
  const chartData = data.map((point) => ({
    bucket: new Date(point.bucket).toLocaleString(),
    count: point.count,
  }));

  if (chartData.length === 0) {
    return <p className="empty-state">No events in this range.</p>;
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <AreaChart data={chartData} margin={{ top: 8, right: 16, left: 0, bottom: 8 }}>
        <CartesianGrid stroke={GRIDLINE_COLOR} strokeDasharray="0" vertical={false} />
        <XAxis dataKey="bucket" tick={{ fontSize: 11, fill: MUTED_INK }} minTickGap={24} />
        <YAxis allowDecimals={false} tick={{ fontSize: 11, fill: MUTED_INK }} width={40} />
        <Tooltip />
        <Area type="monotone" dataKey="count" stroke={SERIES_COLOR} strokeWidth={2} fill={SERIES_COLOR} fillOpacity={0.1} />
      </AreaChart>
    </ResponsiveContainer>
  );
}
