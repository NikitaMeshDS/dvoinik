import {
  BarChart3,
  Users,
  MessageSquare,
  Lightbulb,
  ClipboardCheck,
} from "lucide-react";
const TABS = [
  { id: "overview", label: "Результат", icon: BarChart3 },
  { id: "people", label: "Аудитория", icon: Users },
  { id: "voices", label: "Голоса", icon: MessageSquare },
  { id: "hypotheses", label: "Гипотезы", icon: Lightbulb },
  { id: "validation", label: "Проверка опросом", icon: ClipboardCheck },
] as const;
export type ReportTab = (typeof TABS)[number]["id"];
export default function ReportTabs({
  tab,
  setTab,
}: {
  tab: ReportTab;
  setTab: (tab: ReportTab) => void;
}) {
  return (
    <div className="report-tabs" role="tablist" aria-label="Содержание отчёта">
      {TABS.map(({ id, label, icon: Icon }, index) => (
        <button
          key={id}
          id={"tab-" + id}
          role="tab"
          aria-selected={tab === id}
          aria-controls={"panel-" + id}
          tabIndex={tab === id ? 0 : -1}
          onClick={() => setTab(id)}
          onKeyDown={(event) => {
            const count = TABS.length;
            const next =
              event.key === "ArrowRight"
                ? (index + 1) % count
                : event.key === "ArrowLeft"
                  ? (index + count - 1) % count
                  : event.key === "Home"
                    ? 0
                    : event.key === "End"
                      ? count - 1
                      : null;
            if (next !== null) {
              event.preventDefault();
              setTab(TABS[next].id);
              document.getElementById("tab-" + TABS[next].id)?.focus();
            }
          }}
        >
          <Icon size={16} />
          {label}
        </button>
      ))}
    </div>
  );
}
