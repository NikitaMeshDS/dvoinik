import { useEffect, useId, useState, type Ref } from "react";
import { Download, FileJson, ClipboardCheck, CircleCheck } from "lucide-react";
import { api, ignored, message } from "../../api";
import { Button, Menu, Notice, date } from "../../components";
import type {
  Catalog,
  Experiment,
  Validation,
  SurveyProtocol,
} from "../../types";
import type { ExportAction } from "./types";
import { plural } from "../../data";
import ProtocolEditor, { ProtocolSummary } from "./SurveyProtocol";
import SurveyCoverage from "./SurveyCoverage";
import ValidationMetrics from "./ValidationMetrics";
import SurveyPreparation from "./SurveyPreparation";
import LivePlan from "./LivePlan";
import type { LivePlan as Plan } from "./types";
export default function ValidationPanel({
  record,
  catalog,
  onUpdated,
  onExport,
  plan,
  analyticsError,
  planHeadingRef,
  metricsHeadingRef,
  onDirtyChange,
}: {
  onDirtyChange?: (dirty: boolean) => void;
  plan?: Plan;
  analyticsError?: string;
  planHeadingRef?: Ref<HTMLHeadingElement>;
  metricsHeadingRef?: Ref<HTMLHeadingElement>;
  record: Experiment;
  catalog: Catalog;
  onUpdated: (r: Experiment) => void;
  onExport: ExportAction;
}) {
  const uploadId = useId();
  const [csv, setCsv] = useState(""),
    [filename, setFilename] = useState(""),
    [preview, setPreview] = useState<{
      record: Experiment;
      base_validation: Validation | null;
      preview_id: string;
    } | null>(null),
    [phase, setPhase] = useState<"read" | "preview" | "save" | null>(null),
    [error, setError] = useState("");
  const [savedNotice, setSavedNotice] = useState("");
  const [protocol, setProtocol] = useState<SurveyProtocol>({});
  const busy = phase !== null;
  useEffect(() => {
    onDirtyChange?.(preview !== null || Object.keys(protocol).length > 0);
    return () => onDirtyChange?.(false);
  }, [preview, protocol, onDirtyChange]);
  const discard = () => {
    setPreview(null);
    setCsv("");
    setFilename("");
    setError("");
  };
  const inspect = async (content: string) => {
    setSavedNotice("");
    setPhase("preview");
    setError("");
    try {
      setPreview(
        await api.request(
          "/experiments/" + record.id + "/validation/preview",
          "POST",
          {
            csv: content,
            ...(Object.keys(protocol).length ? { protocol } : {}),
          },
        ),
      );
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setPhase(null);
    }
  };
  const save = async () => {
    if (!preview) return;
    setSavedNotice("");
    setPhase("save");
    setError("");
    try {
      const result = await api.request<Experiment>(
        "/experiments/" + record.id + "/validation",
        "PUT",
        {
          csv,
          base_validation: preview.base_validation,
          ...(Object.keys(protocol).length ? { protocol } : {}),
        },
      );
      onUpdated(result);
      setPreview(null);
      setProtocol({});
      setSavedNotice(
        result.validation
          ? `Проверка сохранена в архиве: ${result.validation.result.survey_n} ${plural(result.validation.result.survey_n, "оценка", "оценки", "оценок")}. Доступна после обновления страницы.`
          : "Проверка сохранена в архиве.",
      );
    } catch (e) {
      if (!ignored(e)) setError(message(e));
    } finally {
      setPhase(null);
    }
  };
  return (
    <>
      <LivePlan
        plan={plan}
        mock={record.mock}
        analyticsError={analyticsError}
        headingRef={planHeadingRef}
      />
      <SurveyPreparation record={record} catalog={catalog} />
      <section
        className="survey-results"
        aria-label="Сопоставление ответов опроса"
      >
        <div className="section-heading">
          <h2>
            <span className="validation-step" aria-hidden="true">
              3
            </span>{" "}
            Сопоставьте ответы
          </h2>
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
          decision — 0 (нет) или 1 (да). Заполните шаблон настоящими ответами,
          удалите незаполненные строки и не добавляйте персональные данные.
        </p>
        <ProtocolEditor
          value={protocol}
          onChange={setProtocol}
          disabled={busy || preview !== null}
        />
        <label className="upload-area">
          <ClipboardCheck size={24} />
          <strong id={uploadId + "-name"}>
            {filename || "Выберите CSV опроса"}
          </strong>
          <span id={uploadId + "-hint"}>UTF-8 · до 5 МБ</span>
          <span className="upload-button" aria-hidden="true">
            Выбрать файл
          </span>
          <input
            className="visually-hidden"
            type="file"
            accept=".csv,text/csv"
            aria-label="CSV живого опроса"
            aria-describedby={uploadId + "-name " + uploadId + "-hint"}
            disabled={busy}
            onChange={async (e) => {
              const file = e.target.files?.[0];
              if (!file || busy) return;
              e.currentTarget.value = "";
              if (
                preview &&
                !window.confirm(
                  "Заменить несохранённый предпросмотр другим файлом?",
                )
              )
                return;
              setPreview(null);
              setSavedNotice("");
              setError("");
              setCsv("");
              setFilename(file.name);
              if (file.size > 5 * 1024 * 1024) {
                setError("Максимальный размер CSV — 5 МБ.");
                return;
              }
              setPhase("read");
              try {
                const content = await file.text();
                setCsv(content);
                await inspect(content);
              } catch {
                setError("Не удалось прочитать CSV. Выберите файл ещё раз.");
              } finally {
                setPhase(null);
              }
            }}
          />
        </label>
        {busy && (
          <p className="help" role="status">
            {phase === "read"
              ? "Читаем CSV…"
              : phase === "save"
                ? "Сохраняем проверку…"
                : "Сопоставляем ответы…"}
          </p>
        )}
        {error && (
          <Notice kind="error">
            {error}
            {preview && (
              <div className="inline-actions">
                <button
                  className="text-link"
                  onClick={() =>
                    onExport("json", "preview", preview.preview_id)
                  }
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
            {preview.base_validation && (
              <Notice kind="warning">
                <strong>
                  Будет заменена проверка от{" "}
                  {date(preview.base_validation.created_at)}.
                </strong>
                <p>
                  Было: {preview.base_validation.result.survey_n} оценок. Будет:{" "}
                  {preview.record.validation!.result.survey_n} оценок.
                </p>
                <p>
                  Предыдущая проверка не хранится в истории. Скачайте
                  сохранённый снимок, если хотите оставить копию.
                </p>
                <button className="text-link" onClick={() => onExport("json")}>
                  Скачать сохранённый снимок
                </button>
              </Notice>
            )}
            <ProtocolSummary protocol={preview.record.validation!.protocol} />
            <SurveyCoverage
              record={record}
              result={preview.record.validation!.result}
              segments={catalog.segments}
            />
            <ValidationMetrics
              result={preview.record.validation!.result}
              segments={catalog.segments}
              headingRef={metricsHeadingRef}
            />
            <div className="selection-bar survey-save-actions">
              <span>Предпросмотр · ещё не сохранён</span>
              <Button kind="primary" disabled={busy} onClick={save}>
                {phase === "save"
                  ? "Сохраняем…"
                  : preview.base_validation
                    ? "Заменить проверку"
                    : "Сохранить проверку"}
              </Button>
              <button className="text-link" disabled={busy} onClick={discard}>
                Отменить предпросмотр
              </button>
            </div>
          </>
        ) : record.validation ? (
          <>
            <p className="help">
              Сохранено {date(record.validation.created_at)} · ответы
              предоставлены пользователем.
            </p>
            <ProtocolSummary protocol={record.validation.protocol} />
            <SurveyCoverage
              record={record}
              result={record.validation.result}
              segments={catalog.segments}
            />
            <ValidationMetrics
              result={record.validation.result}
              segments={catalog.segments}
              headingRef={metricsHeadingRef}
            />
          </>
        ) : (
          <Notice>
            Живая проверка ещё не проведена. Добавьте ответы, чтобы измерить
            расхождение с симуляцией.
          </Notice>
        )}
        {savedNotice && (
          <div
            className="save-confirmation"
            role="status"
            aria-label="Проверка сохранена"
          >
            <CircleCheck size={20} aria-hidden="true" />
            <p>{savedNotice}</p>
          </div>
        )}
        <p className="help">
          Ошибка взвешивается по числу ответов. Для общего рейтинга нужны оценки
          каждого варианта и одинаковые доли сегментов. Новая загрузка заменяет
          прежний опрос.
        </p>
      </section>
    </>
  );
}
