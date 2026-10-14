import { useState } from "react";
import { Download, FileJson, ClipboardCheck } from "lucide-react";
import { api, ignored, message } from "../../api";
import { Button, Menu, Notice, date } from "../../components";
import type { Experiment, Validation } from "../../types";
import type { ExportAction } from "./types";
import ValidationMetrics from "./ValidationMetrics";
export default function ValidationPanel({
  record,
  onUpdated,
  onExport,
}: {
  record: Experiment;
  onUpdated: (r: Experiment) => void;
  onExport: ExportAction;
}) {
  const [csv, setCsv] = useState(""),
    [filename, setFilename] = useState(""),
    [preview, setPreview] = useState<{
      record: Experiment;
      base_validation: Validation | null;
      preview_id: string;
    } | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState("");
  const inspect = async (content: string) => {
    setBusy(true);
    setError("");
    try {
      setPreview(
        await api.request(
          "/experiments/" + record.id + "/validation/preview",
          "POST",
          { csv: content },
        ),
      );
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  const save = async () => {
    if (!preview) return;
    setBusy(true);
    setError("");
    try {
      const result = await api.request<Experiment>(
        "/experiments/" + record.id + "/validation",
        "PUT",
        { csv, base_validation: preview.base_validation },
      );
      onUpdated(result);
      setPreview(null);
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setBusy(false);
    }
  };
  return (
    <>
      <div className="section-heading">
        <h2>Сопоставьте ответы с живым опросом</h2>
        <Menu label="Файлы проверки">
          <button onClick={() => onExport("csv", "survey-template")}>
            <Download size={17} />
            Шаблон CSV
          </button>
          {record.validation && (
            <button onClick={() => onExport("json", "validation")}>
              <FileJson size={17} />
              Метрики JSON
            </button>
          )}
          {preview && (
            <button
              onClick={() => onExport("json", "preview", preview.preview_id)}
            >
              <FileJson size={17} />
              Предпросмотр JSON
            </button>
          )}
        </Menu>
      </div>
      <p className="help">
        CSV: segment, variant, decision. Одна оценка предложения на строку;
        decision — 0 или 1. Нули в шаблоне замените настоящими ответами.
      </p>
      <label className="upload-area">
        <ClipboardCheck size={24} />
        <strong>{filename || "Выберите CSV опроса"}</strong>
        <span>UTF-8 · до 5 МБ</span>
        <input
          type="file"
          accept=".csv,text/csv"
          aria-label="CSV живого опроса"
          disabled={busy}
          onChange={async (e) => {
            const file = e.target.files?.[0];
            if (!file) return;
            setPreview(null);
            setError("");
            if (file.size > 5 * 1024 * 1024) {
              setError("Максимальный размер CSV — 5 МБ.");
              return;
            }
            const content = await file.text();
            setCsv(content);
            setFilename(file.name);
            await inspect(content);
          }}
        />
      </label>
      {busy && (
        <p className="help" role="status">
          Сопоставляем ответы…
        </p>
      )}
      {error && (
        <Notice kind="error">
          {error}
          {preview && (
            <div className="inline-actions">
              <button
                className="text-link"
                onClick={() => onExport("json", "preview", preview.preview_id)}
              >
                Скачать полный предпросмотр
              </button>
              <button className="text-link" onClick={() => inspect(csv)}>
                Заново сверить опрос
              </button>
            </div>
          )}
        </Notice>
      )}
      {preview ? (
        <>
          <div className="selection-bar">
            <span>Предпросмотр · ещё не сохранён</span>
            <Button kind="primary" disabled={busy} onClick={save}>
              Сохранить проверку
            </Button>
          </div>
          <ValidationMetrics result={preview.record.validation!.result} />
        </>
      ) : record.validation ? (
        <>
          <p className="help">
            Сохранено {date(record.validation.created_at)} · ответы
            предоставлены пользователем.
          </p>
          <ValidationMetrics result={record.validation.result} />
        </>
      ) : (
        <Notice>
          Живая проверка ещё не проведена. Добавьте ответы, чтобы измерить
          расхождение с симуляцией.
        </Notice>
      )}
      <p className="help">
        Ошибка взвешивается по числу ответов. Ранги сравниваются на составе
        загруженного опроса; для содержательных выводов оценивайте варианты на
        сопоставимых аудиториях.
      </p>
    </>
  );
}
