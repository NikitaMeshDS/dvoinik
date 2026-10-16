import { useEffect, useState } from "react";
import { Download, ArrowRight } from "lucide-react";
import { api, download, ignored, message } from "./api";
import { Button, Modal, Notice, decimal, percent, date } from "./components";
import type { Comparison, Experiment } from "./types";
export function ComparisonDialog({
  ids,
  records,
  onClose,
  onError,
}: {
  ids: string[];
  records: Experiment[];
  onClose: () => void;
  onError: (e: unknown) => void;
}) {
  const [left, setLeft] = useState(ids[0] ?? ""),
    [right, setRight] = useState(ids[1] ?? ""),
    [result, setResult] = useState<Comparison | null>(null),
    [error, setError] = useState("");
  useEffect(() => {
    let alive = true;
    setResult(null);
    setError("");
    if (!left || !right || left === right) return;
    api
      .request<Comparison>("/compare", "POST", {
        left_id: left,
        right_id: right,
      })
      .then((r) => {
        if (alive) setResult(r);
      })
      .catch((e) => {
        if (alive && !ignored(e)) setError(message(e));
      });
    return () => {
      alive = false;
    };
  }, [left, right]);
  return (
    <Modal title="Сравнение исследований" onClose={onClose}>
      <div className="compare-pickers">
        <label className="field">
          <span>Исходный запуск</span>
          <select value={left} onChange={(e) => setLeft(e.target.value)}>
            <option value="">Выберите исследование</option>
            {records.map((r) => (
              <option value={r.id} key={r.id}>
                {r.scenario.title} · {date(r.created_at)} · {r.id}
              </option>
            ))}
          </select>
        </label>
        <ArrowRight size={20} />
        <label className="field">
          <span>Следующая итерация</span>
          <select value={right} onChange={(e) => setRight(e.target.value)}>
            <option value="">Выберите исследование</option>
            {records.map((r) => (
              <option value={r.id} key={r.id}>
                {r.scenario.title} · {date(r.created_at)} · {r.id}
              </option>
            ))}
          </select>
        </label>
      </div>
      {left === right && left && <Notice>Выберите два разных запуска.</Notice>}
      {error && <Notice kind="error">{error}</Notice>}
      {result ? (
        <>
          <Notice>
            Дельты описательные: они не доказывают причинный эффект или
            статистическую значимость. Буквы связывают предложения; проверьте их
            тексты.
          </Notice>
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Предложение</th>
                  <th>Исходный</th>
                  <th>Итерация</th>
                  <th>Дельта, п.п.</th>
                  <th>Ответов</th>
                </tr>
              </thead>
              <tbody>
                {result.comparison.variants.map((r) => (
                  <tr key={r.variant}>
                    <td>{r.variant}</td>
                    <td>{percent(r.left)}</td>
                    <td>{percent(r.right)}</td>
                    <td>
                      {r.delta_pp === null
                        ? "—"
                        : (r.delta_pp > 0 ? "+" : "") + decimal(r.delta_pp)}
                    </td>
                    <td>
                      {r.left_n ?? "—"} / {r.right_n ?? "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <details className="disclosure">
            <summary>
              Изменённые условия ({result.comparison.changes.length})
            </summary>
            <div className="disclosure-content">
              {result.comparison.changes.length ? (
                result.comparison.changes.map((c) => (
                  <div className="comparison-change" key={c.field}>
                    <strong>{c.label}</strong>
                    <div>
                      <p>
                        {typeof c.before === "string"
                          ? c.before
                          : JSON.stringify(c.before)}
                      </p>
                      <p>
                        {typeof c.after === "string"
                          ? c.after
                          : JSON.stringify(c.after)}
                      </p>
                    </div>
                  </div>
                ))
              ) : (
                <p>Зафиксированные условия совпадают.</p>
              )}
            </div>
          </details>
          <details className="disclosure">
            <summary>Разница по сегментам</summary>
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Вариант</th>
                    <th>Сегмент</th>
                    <th>Исходный</th>
                    <th>Итерация</th>
                    <th>Дельта, п.п.</th>
                  </tr>
                </thead>
                <tbody>
                  {result.comparison.segments.map((r) => (
                    <tr key={r.variant + r.segment}>
                      <td>{r.variant}</td>
                      <td>{r.segment}</td>
                      <td>{percent(r.left)}</td>
                      <td>{percent(r.right)}</td>
                      <td>{r.delta_pp === null ? "—" : decimal(r.delta_pp)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </details>
          <div className="modal-actions">
            <Button
              onClick={() =>
                download("/compare/export", {
                  left_id: left,
                  right_id: right,
                }).catch(onError)
              }
            >
              <Download size={17} />
              Скачать сравнение JSON
            </Button>
          </div>
        </>
      ) : left && right && left !== right && !error ? (
        <p className="help" role="status">
          Сопоставляем снимки…
        </p>
      ) : null}
    </Modal>
  );
}
export function ImportDialog({
  onClose,
  onImported,
}: {
  onClose: () => void;
  onImported: (r: Experiment) => void;
}) {
  const [content, setContent] = useState(""),
    [name, setName] = useState(""),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const save = async () => {
    setBusy(true);
    setError("");
    try {
      onImported(await api.request<Experiment>("/import", "POST", { content }));
      onClose();
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal title="Импорт исследования" onClose={onClose}>
      <p>
        Загрузите полный JSON Двойника. Сервер проверит снимок и пересчитает
        показатели; импорт получит новый локальный ID.
      </p>
      <label className="upload-area">
        <strong>{name || "Выберите JSON исследования"}</strong>
        <span>До 5 МБ · форматы 1 и 2</span>
        <input
          type="file"
          accept=".json,application/json"
          aria-label="JSON исследования"
          disabled={busy}
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setError("");
            setContent("");
            if (file.size > 5 * 1024 * 1024) {
              setError("Максимальный размер JSON — 5 МБ.");
              return;
            }
            setName(file.name);
            setContent(await file.text());
          }}
        />
      </label>
      {error && <Notice kind="error">{error}</Notice>}
      <div className="modal-actions">
        <Button kind="primary" disabled={!content || busy} onClick={save}>
          {busy ? "Импортируем…" : "Импортировать"}
        </Button>
      </div>
    </Modal>
  );
}
