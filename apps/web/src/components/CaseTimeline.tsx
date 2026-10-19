"use client";

// Vis-timeline wrapper: one group lane per source_type, click event -> onSelect.
// Loaded behind next/dynamic(..., { ssr: false }) — window is always available.
import { useEffect, useMemo, useRef } from "react";
import { Timeline } from "vis-timeline/standalone";
import { DataSet } from "vis-data";
import "vis-timeline/styles/vis-timeline-graph2d.css";

export type TimelineEvent = {
  id: number;
  event_ts_utc: string;
  label: string | null;
  source_type: string;
  artifact_id: number;
};

export default function CaseTimeline({
  events,
  onSelect,
}: {
  events: TimelineEvent[];
  onSelect: (artifactId: number) => void;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const byId = useMemo(() => new Map(events.map((e) => [e.id, e])), [events]);

  const { items, groups } = useMemo(() => {
    const groupIds = [...new Set(events.map((e) => e.source_type))].sort();
    const groups = new DataSet(
      groupIds.map((g) => ({ id: g, content: g.replace(/_/g, " ") }))
    );
    const items = new DataSet(
      events.map((e) => ({
        id: e.id,
        content: e.label ?? `event ${e.id}`,
        title: `${e.event_ts_utc} — ${e.label ?? ""}`,
        start: e.event_ts_utc,
        group: e.source_type,
      }))
    );
    return { items, groups };
  }, [events]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const tl = new Timeline(el, items, groups, {
      stack: true,
      showCurrentTime: false,
      zoomMin: 1000 * 60 * 60,
    });
    const handler = (props: { items: (number | string)[] }) => {
      const first = props.items?.[0];
      const ev = byId.get(Number(first));
      if (ev) onSelect(ev.artifact_id);
    };
    tl.on("select", handler as never);
    return () => {
      tl.off("select", handler as never);
      tl.destroy();
    };
  }, [items, groups, byId, onSelect]);

  return <div ref={containerRef} className="vis-timeline-host" />;
}
