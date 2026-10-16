import { useRef } from "react";
import {
  Plus,
  ArrowUpRight,
  Upload,
  GitCompare,
  Check,
  ChevronLeft,
  ChevronRight,
  RefreshCw,
  FlaskConical,
} from "lucide-react";
import {
  Button,
  Heading,
  Empty,
  Menu,
  Notice,
  date,
  percent,
} from "./components";
import { type Experiment } from "./types";
import { chronological, plural } from "./data";
import ResponsePreview from "./features/research/ResponsePreview";
import ResearchFilters, {
  type ResearchFilterState,
} from "./features/research/ResearchFilters";
export type LibraryState = ResearchFilterState & {
  page: number;
  compare: boolean;
  selected: string[];
};
export const INITIAL_LIBRARY: LibraryState = {
  search: "",
  mode: "all",
  survey: "all",
  page: 0,
  filtersOpen: false,
  compare: false,
  selected: [],
};
export default function Library({
  records,
  state,
  onState,
  onNew,
  onOpen,
  onImport,
  onSample,
  onCompare,
  pending,
  loading = false,
  error = "",
  onReload,
}: {
  records: Experiment[];
  state: LibraryState;
  onState: (s: LibraryState) => void;
  onNew: () => void;
  onOpen: (id: string) => void;
  onImport: () => void;
  onSample: () => void;
  onCompare: (ids: string[]) => void;
  pending: Set<string>;
  loading?: boolean;
  error?: string;
  onReload?: () => void;
}) {
  const searchRef = useRef<HTMLInputElement>(null);
  const patch = (p: Partial<LibraryState>) => onState({ ...state, ...p });
  const llmCount = records.filter((r) => !r.mock).length;
  const surveyCount = records.filter((r) => r.validation).length;
  const filtered = chronological(records).filter((r) => {
    const text = [
      r.scenario.title,
      r.scenario.question,
      ...Object.values(r.scenario.variants),
      r.model,
      r.id,
    ]
      .join(" ")
      .toLowerCase();
    return (
      text.includes(state.search.toLowerCase()) &&
      (state.mode === "all" || (state.mode === "demo") === r.mock) &&
      (state.survey === "all" || (state.survey === "yes") === !!r.validation)
    );
  });
  const pages = Math.max(1, Math.ceil(filtered.length / 8)),
    page = Math.min(state.page, pages - 1);
  const toggle = (id: string) =>
    patch({
      selected: state.selected.includes(id)
        ? state.selected.filter((v) => v !== id)
        : state.selected.length < 2
          ? [...state.selected, id]
          : state.selected,
    });
  return (
    <>
      <Heading
        title="Исследования"
        description="Ваши гипотезы, ответы и следующие итерации — в одном месте."
        action={
          <div className="heading-actions">
            <Button kind="primary" onClick={onNew}>
              <Plus size={18} />
              Новое исследование
            </Button>
            <Menu label="Действия с исследованиями">
              <button onClick={onImport}>
                <Upload size={17} />
                Импорт JSON
              </button>
              <button
                disabled={records.length < 2}
                onClick={() => patch({ compare: !state.compare, selected: [] })}
              >
                <GitCompare size={17} />
                {state.compare ? "Завершить выбор" : "Сравнить исследования"}
              </button>
            </Menu>
          </div>
        }
      />
      {error && (
        <Notice kind="error">
          {error}
          <div className="inline-actions">
            <Button onClick={onReload}>
              <RefreshCw size={16} />
              Повторить загрузку исследований
            </Button>
          </div>
        </Notice>
      )}
      {loading && records.length === 0 ? (
        <div
          className="archive-loading"
          role="status"
          aria-label="Загрузка исследований"
        >
          <p>Открываем ваши исследования…</p>
          <div />
          <div />
          <div />
        </div>
      ) : records.length === 0 && !error ? (
        <Empty
          title="Ваша лаборатория готова"
          action={
            <button className="text-link" onClick={onSample}>
              Посмотреть пример исследования
              <ArrowUpRight size={16} />
            </button>
          }
        >
          Выберите сценарий, сформулируйте предложения и узнайте, какие вопросы
          стоит задать живой аудитории.
        </Empty>
      ) : records.length > 0 ? (
        <>
          <section className="library-surface" aria-label="Архив исследований">
            <div className="library-overview">
              <div>
                <strong>{records.length}</strong>
                <span>
                  {plural(
                    records.length,
                    "исследование",
                    "исследования",
                    "исследований",
                  )}
                </span>
              </div>
              {llmCount > 0 && (
                <div>
                  <strong>{llmCount}</strong>
                  <span>
                    {plural(llmCount, "запуск", "запуска", "запусков")} LLM
                  </span>
                </div>
              )}
              <div className={surveyCount ? "has-survey" : "no-survey"}>
                {surveyCount > 0 ? (
                  <>
                    <Check size={14} />
                    <span>
                      {surveyCount}{" "}
                      {plural(
                        surveyCount,
                        "сопоставление",
                        "сопоставления",
                        "сопоставлений",
                      )}{" "}
                      с опросом
                    </span>
                  </>
                ) : (
                  <span>Опросы ещё не загружены</span>
                )}
              </div>
            </div>
            <ResearchFilters
              searchRef={searchRef}
              state={state}
              onChange={(changes) =>
                patch({
                  ...changes,
                  page: changes.filtersOpen === undefined ? 0 : state.page,
                })
              }
            />
            {loading && (
              <p className="refresh-status" role="status">
                Обновляем исследования…
              </p>
            )}
            {state.compare && (
              <div className="selection-bar">
                <span>
                  Выберите два исследования: {state.selected.length} / 2
                </span>
                <Button
                  kind="primary"
                  disabled={state.selected.length !== 2}
                  onClick={() => onCompare(state.selected)}
                >
                  <GitCompare size={17} />
                  Сравнить
                </Button>
                <button
                  className="text-link"
                  onClick={() => patch({ compare: false, selected: [] })}
                >
                  Отмена
                </button>
              </div>
            )}
            {filtered.length === 0 ? (
              <Empty
                title="Совпадений нет"
                action={
                  <Button
                    onClick={() => {
                      searchRef.current?.focus();
                      patch({
                        search: "",
                        mode: "all",
                        survey: "all",
                        page: 0,
                      });
                    }}
                  >
                    Сбросить поиск и фильтры
                  </Button>
                }
              >
                Измените запрос или фильтры, чтобы увидеть другие исследования.
              </Empty>
            ) : (
              <div className="study-list">
                <div className="study-list-head" aria-hidden="true">
                  <span>Исследование</span>
                  <span>Согласия по предложениям</span>
                  <span>Лидер</span>
                </div>
                {filtered.slice(page * 8, page * 8 + 8).map((r) => {
                  const valid = Object.entries(r.report).filter(
                      ([, v]) => v.n > 0,
                    ),
                    best = valid.length
                      ? Math.max(...valid.map(([, v]) => v.conversion!))
                      : null,
                    leaders = valid
                      .filter(([, v]) => Math.abs(v.conversion! - best!) < 1e-9)
                      .map(([v]) => v);
                  return (
                    <div className="study-row" key={r.id}>
                      {state.compare && (
                        <input
                          type="checkbox"
                          aria-label={
                            "Выбрать " +
                            r.scenario.title +
                            ", " +
                            date(r.created_at) +
                            ", " +
                            r.id
                          }
                          checked={state.selected.includes(r.id)}
                          disabled={
                            !state.selected.includes(r.id) &&
                            state.selected.length === 2
                          }
                          onChange={() => toggle(r.id)}
                        />
                      )}
                      <button
                        className="study-main"
                        onClick={() => onOpen(r.id)}
                      >
                        <span className="study-icon" aria-hidden="true">
                          <FlaskConical size={21} />
                        </span>
                        <span className="study-context">
                          <strong>{r.scenario.title}</strong>
                          <span className="study-question">
                            {r.scenario.question}
                          </span>
                          <small>
                            {date(r.created_at)} · {r.n.toLocaleString("ru-RU")}{" "}
                            {plural(r.n, "профиль", "профиля", "профилей")} ·{" "}
                            {r.model}
                          </small>
                          <span className="study-tags">
                            <i className={r.mock ? "demo" : "llm"}>
                              {r.mock ? "Демо" : "LLM"}
                            </i>
                            {r.validation && (
                              <i>
                                <Check size={12} />
                                Опрос загружен
                              </i>
                            )}
                            {pending.has(r.id) && (
                              <i className="warning">Ожидает записи</i>
                            )}
                          </span>
                        </span>
                        <ResponsePreview report={r.report} />
                        <span className="study-result">
                          <b>{percent(best)}</b>
                          <small>
                            {leaders.length
                              ? "Вариант " + leaders.join(" / ")
                              : "Нет ответов"}
                          </small>
                        </span>
                        <ArrowUpRight size={19} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
            <div className="pagination">
              <span>
                {filtered.length}{" "}
                {plural(
                  filtered.length,
                  "исследование",
                  "исследования",
                  "исследований",
                )}{" "}
                {pages > 1 && (
                  <>
                    {" "}
                    · страница {page + 1} из {pages}
                  </>
                )}
              </span>
              {pages > 1 && (
                <div>
                  <Button
                    aria-label="Предыдущая страница"
                    disabled={page === 0}
                    onClick={() => patch({ page: page - 1 })}
                  >
                    <ChevronLeft size={17} />
                  </Button>
                  <Button
                    aria-label="Следующая страница"
                    disabled={page === pages - 1}
                    onClick={() => patch({ page: page + 1 })}
                  >
                    <ChevronRight size={17} />
                  </Button>
                </div>
              )}
            </div>
          </section>
        </>
      ) : null}
    </>
  );
}
