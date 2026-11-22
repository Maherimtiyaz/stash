import { useState } from "react";
import { api } from "../api";
import { Empty, Icon, Reel, Spinner } from "../components/ui";
import { addDays, isoDate, lookStyle, parseDay, title } from "../lib/format";
import { useApp, useLoad } from "../store";

/** The week: drag reels from "someday" onto a day (or tap one, then tap a day). */
export function PlanView() {
  const { openSave, toast, changed } = useApp();
  const [start, setStart] = useState<string | undefined>(undefined);
  const [picked, setPicked] = useState<number | null>(null);
  const [over, setOver] = useState<string | null>(null);
  const week = useLoad(() => api.plan(start), [start]);
  const w = week.data;

  async function planOn(id: number, day: string | null) {
    try {
      await api.update(id, { plan_day: day });
      setPicked(null);
      toast(day ? `Planned for ${parseDay(day).toLocaleDateString(undefined, { weekday: "long" })}` : "Back to someday");
      changed();
    } catch (e) {
      toast((e as Error).message);
    }
  }

  const shift = (n: number) => w && setStart(isoDate(addDays(parseDay(w.start), n)));
  const planned = w ? w.days.reduce((n, d) => n + d.saves.length, 0) : 0;
  const doneCount = w ? w.days.reduce((n, d) => n + d.saves.filter((s) => s.progress === "done").length, 0) : 0;
  const thisWeek = w && w.today >= w.days[0].date && w.today <= w.days[6].date;
  const range = w ? `${parseDay(w.days[0].date).toLocaleDateString(undefined, { day: "numeric", month: "short" })} – ${parseDay(w.days[6].date).toLocaleDateString(undefined, { day: "numeric", month: "short" })}` : "";

  const dropProps = (day: string | null) => ({
    onDragOver: (e: React.DragEvent) => { e.preventDefault(); setOver(day ?? "pile"); },
    onDragLeave: () => setOver(null),
    onDrop: (e: React.DragEvent) => {
      e.preventDefault();
      setOver(null);
      const id = Number(e.dataTransfer.getData("text/plain"));
      if (id) planOn(id, day);
    },
  });
  const dragProps = (id: number) => ({
    draggable: true,
    onDragStart: (e: React.DragEvent) => { e.dataTransfer.setData("text/plain", String(id)); e.dataTransfer.effectAllowed = "move"; },
  });

  return (
    <section className="view plan">
      <header className="page-head row-head">
        <div>
          <span className="kicker">{range}</span>
          <h1 className="mega small">{thisWeek ? "This week" : "Week plan"}</h1>
        </div>
        <div className="weeknav">
          <button className="round" onClick={() => shift(-7)} aria-label="Previous week"><Icon name="left" /></button>
          {!thisWeek && w && <button className="pill" onClick={() => setStart(undefined)}>Today</button>}
          <button className="round" onClick={() => shift(7)} aria-label="Next week"><Icon name="right" /></button>
        </div>
      </header>

      {week.error && <p className="error">{week.error}</p>}
      {!w && !week.error && <Spinner />}
      {w && (
        <>
          <div className="scoreboard">
            <span className="count c1"><b>{planned}</b> planned</span>
            <span className="count c2"><b>{doneCount}</b> done</span>
            <span className="count c3"><b>{w.pile.length}</b> someday</span>
          </div>

          <div className={`someday${over === "pile" ? " over" : ""}`} {...dropProps(null)}>
            <div className="someday-head">
              <h2>Someday</h2>
              <p>{picked ? "Now tap a day below" : "Drag a reel onto a day, or tap one and then a day"}</p>
            </div>
            {w.pile.length ? (
              <div className="someday-row">
                {w.pile.map((s) => (
                  <div key={s.id} className={`pick${picked === s.id ? " on" : ""}`}>
                    <Reel save={s} size="sm" onOpen={() => setPicked(picked === s.id ? null : s.id)} {...dragProps(s.id)} />
                  </div>
                ))}
              </div>
            ) : <Empty art="🎉" title="Nothing waiting"><p>Everything on your to-try list has a day.</p></Empty>}
          </div>

          <div className="week">
            {w.days.map((d) => {
              const dt = parseDay(d.date);
              const isToday = d.date === w.today;
              return (
                <div key={d.date} className={`day${isToday ? " today" : ""}${picked ? " ready" : ""}${over === d.date ? " over" : ""}`}
                  {...dropProps(d.date)}
                  role={picked ? "button" : undefined} tabIndex={picked ? 0 : undefined}
                  onClick={() => picked && planOn(picked, d.date)}
                  onKeyDown={(e) => picked && (e.key === "Enter" || e.key === " ") && planOn(picked, d.date)}>
                  <div className="day-head">
                    <span>{isToday ? "Today" : dt.toLocaleDateString(undefined, { weekday: "long" })}</span>
                    <b>{dt.getDate()}</b>
                  </div>
                  <div className="day-items">
                    {d.saves.map((s) => (
                      <button key={s.id} className={`slip${s.progress === "done" ? " done" : ""}`} style={lookStyle(s)} {...dragProps(s.id)}
                        onClick={(e) => { e.stopPropagation(); openSave(s.id); }}>
                        {s.progress === "done" && <Icon name="check" size={14} />}<span>{title(s)}</span>
                      </button>
                    ))}
                    {!d.saves.length && <span className="free">{picked ? "Drop it here" : "Free"}</span>}
                  </div>
                </div>
              );
            })}
          </div>
          <p className="hint">Tap a planned slip to mark it tried or move it. Drag it back to Someday to unplan.</p>
        </>
      )}
    </section>
  );
}
