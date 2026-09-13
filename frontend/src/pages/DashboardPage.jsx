import { useEffect, useState } from "react";

import { statsTimeline, statsTop } from "../api/events";
import TimeRangeFilter from "../components/TimeRangeFilter";
import TimelineChart from "../components/TimelineChart";
import TopNTable from "../components/TopNTable";

// Picks a bucket size that keeps the timeline readable across very
// different range lengths — a 15-minute range bucketed by day would be one
// bar; a 7-day range bucketed by minute would be unreadably dense.
function chooseInterval(startTime, endTime) {
  if (!startTime || !endTime) return "hour";
  const spanMs = new Date(endTime) - new Date(startTime);
  const hour = 60 * 60 * 1000;
  if (spanMs <= 2 * hour) return "minute";
  if (spanMs <= 3 * 24 * hour) return "hour";
  return "day";
}

function defaultRange() {
  const end = new Date();
  const start = new Date(end.getTime() - 60 * 60 * 1000);
  return { startTime: start.toISOString(), endTime: end.toISOString() };
}

export default function DashboardPage() {
  const [range, setRange] = useState(defaultRange);
  const [timeline, setTimeline] = useState([]);
  const [topIps, setTopIps] = useState([]);
  const [topUsers, setTopUsers] = useState([]);
  const [topEventTypes, setTopEventTypes] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    const interval = chooseInterval(range.startTime, range.endTime);
    const params = { start_time: range.startTime, end_time: range.endTime };

    Promise.all([
      statsTimeline({ ...params, interval }),
      statsTop("ip", params),
      statsTop("user", params),
      statsTop("event_type", params),
    ])
      .then(([timelineData, ips, users, eventTypes]) => {
        if (cancelled) return;
        setTimeline(timelineData);
        setTopIps(ips);
        setTopUsers(users);
        setTopEventTypes(eventTypes);
      })
      .catch((err) => {
        if (!cancelled) setError(err.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [range]);

  return (
    <div className="dashboard-page">
      <h1>Dashboard</h1>
      <TimeRangeFilter onChange={setRange} />
      {error && <p className="form-error">{error}</p>}
      {loading ? (
        <p>Loading…</p>
      ) : (
        <>
          <section className="dashboard-timeline">
            <h2>Event Timeline</h2>
            <TimelineChart data={timeline} />
          </section>
          <section className="dashboard-top-n">
            <TopNTable title="Top Source IPs" items={topIps} />
            <TopNTable title="Top Users" items={topUsers} />
            <TopNTable title="Top Event Types" items={topEventTypes} />
          </section>
        </>
      )}
    </div>
  );
}
