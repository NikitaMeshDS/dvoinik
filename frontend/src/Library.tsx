import {
  Search,
  Plus,
  ArrowUpRight,
  Upload,
  GitCompare,
  Check,
  ChevronLeft,
  ChevronRight,
} from "lucide-react";
import { Button, Heading, Empty, Menu, date, percent } from "./components";
import { type Experiment } from "./types";
import { chronological, plural } from "./data";
export type LibraryState = {
  search: string;
  mode: string;
  survey: string;
  page: number;
  compare: boolean;
  selected: string[];
};
export const INITIAL_LIBRARY: LibraryState = {
  search: "",
  mode: "all",
  survey: "all",
  page: 0,
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
}) {
  const patch = (p: Partial<LibraryState>) => onState({ ...state, ...p });
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
      {records.length === 0 ? (
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
      ) : (
        <>
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
            <div>
              <strong>{records.filter((r) => !r.mock).length}</strong>
              <span>
                {plural(
                  records.filter((r) => !r.mock).length,
                  "запуск",
                  "запуска",
                  "запусков",
                )}{" "}
                LLM
              </span>
            </div>
            <div>
              <strong>{records.filter((r) => r.validation).length}</strong>
              <span>
                {plural(
                  records.filter((r) => r.validation).length,
                  "сопоставление",
                  "сопоставления",
                  "сопоставлений",
                )}{" "}
                с опросом
              </span>
            </div>
          </div>
          <div className="filter-bar">
            <label className="search">
              <Search size={18} />
              <input
                aria-label="Поиск исследований"
                placeholder="Найти исследование, предложение или модель"
                value={state.search}
                onChange={(e) => patch({ search: e.target.value, page: 0 })}
              />
            </label>
            <select
              aria-label="Режим исследований"
              value={state.mode}
              onChange={(e) => patch({ mode: e.target.value, page: 0 })}
            >
              <option value="all">Все модели</option>
              <option value="demo">Демо</option>
              <option value="llm">LLM</option>
            </select>
            <select
              aria-label="Наличие опроса"
              value={state.survey}
              onChange={(e) => patch({ survey: e.target.value, page: 0 })}
            >
              <option value="all">Все проверки</option>
              <option value="yes">С опросом</option>
              <option value="no">Без опроса</option>
            </select>
          </div>
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
            <Empty title="Совпадений нет">
              Измените запрос или фильтры, чтобы увидеть другие исследования.
            </Empty>
          ) : (
            <div className="study-list">
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
                    <button className="study-main" onClick={() => onOpen(r.id)}>
                      <span className="study-icon" aria-hidden="true">
                        {r.scenario.title[0]}
                      </span>
                      <span>
                        <strong>{r.scenario.title}</strong>
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
                      <span className="study-result">
                        <b>{percent(best, 0)}</b>
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
              · страница {page + 1} из {pages}
            </span>
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
          </div>
        </>
      )}
    </>
  );
}
