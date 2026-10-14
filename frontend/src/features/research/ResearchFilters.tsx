import { useId, useRef, type RefObject } from "react";
import { Search, SlidersHorizontal, X } from "lucide-react";
import { Button } from "../../components";
export type ResearchFilterState = {
  search: string;
  mode: string;
  survey: string;
  filtersOpen: boolean;
};
export default function ResearchFilters({
  state,
  onChange,
  searchRef,
}: {
  state: ResearchFilterState;
  onChange: (patch: Partial<ResearchFilterState>) => void;
  searchRef: RefObject<HTMLInputElement | null>;
}) {
  const filterId = useId();
  const toggleRef = useRef<HTMLButtonElement>(null);
  const activeFilters =
    Number(state.mode !== "all") + Number(state.survey !== "all");
  return (
    <>
      <div className="filter-bar">
        <div className="search" role="search" aria-label="Поиск в архиве">
          <Search size={18} aria-hidden="true" />
          <input
            ref={searchRef}
            aria-label="Поиск исследований"
            placeholder="Найти исследование…"
            value={state.search}
            onChange={(e) => onChange({ search: e.target.value })}
          />
          {state.search && (
            <button
              className="icon-button"
              aria-label="Очистить поиск"
              onClick={() => {
                searchRef.current?.focus();
                onChange({ search: "" });
              }}
            >
              <X size={16} />
            </button>
          )}
        </div>
        <Button
          ref={toggleRef}
          className={
            activeFilters ? "filter-toggle is-active" : "filter-toggle"
          }
          aria-expanded={state.filtersOpen}
          aria-controls={filterId}
          aria-label={
            activeFilters ? "Фильтры, активно: " + activeFilters : "Фильтры"
          }
          onClick={() => onChange({ filtersOpen: !state.filtersOpen })}
        >
          <SlidersHorizontal size={16} />
          <span>Фильтры</span>
          {activeFilters > 0 && <b aria-hidden="true">{activeFilters}</b>}
        </Button>
        {activeFilters > 0 && (
          <button
            className="text-link filter-reset"
            onClick={() => {
              toggleRef.current?.focus();
              onChange({ mode: "all", survey: "all" });
            }}
          >
            Сбросить фильтры
          </button>
        )}
      </div>
      <div className="filter-panel" id={filterId} hidden={!state.filtersOpen}>
        <label className="field">
          <span>Режим исследования</span>
          <select
            aria-label="Режим исследований"
            value={state.mode}
            onChange={(e) => onChange({ mode: e.target.value })}
          >
            <option value="all">Все режимы</option>
            <option value="demo">Демо</option>
            <option value="llm">LLM</option>
          </select>
        </label>
        <label className="field">
          <span>Сопоставление с опросом</span>
          <select
            aria-label="Наличие опроса"
            value={state.survey}
            onChange={(e) => onChange({ survey: e.target.value })}
          >
            <option value="all">Все исследования</option>
            <option value="yes">С опросом</option>
            <option value="no">Без опроса</option>
          </select>
        </label>
      </div>
    </>
  );
}
