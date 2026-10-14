import { ArrowLeft, Users, Square } from "lucide-react";
import { Button, Heading, Notice } from "./components";
import type { Job } from "./types";
export default function JobView({
  job,
  error,
  onRetry,
  onCancel,
  cancelBusy,
  onBack,
  onBackground,
}: {
  job: Job | null;
  error: string;
  onRetry: () => void;
  onCancel: () => void;
  cancelBusy: boolean;
  onBack: () => void;
  onBackground: () => void;
}) {
  const done = job?.done ?? 0,
    total = job?.total ?? 1,
    failed = job?.status === "failed",
    cancelled = job?.status === "cancelled",
    cancelling = job?.status === "cancelling",
    terminal = failed || cancelled;
  return (
    <>
      <Heading
        title={
          cancelled
            ? "Исследование остановлено"
            : failed
              ? "Исследование не завершено"
              : "Двойники знакомятся с предложениями"
        }
        description={
          cancelled
            ? "Частичный результат не сохранён. Можно настроить и запустить новое исследование."
            : "Можно продолжать работу: запуск выполняется на сервере."
        }
      />
      {error && (
        <Notice kind="error">
          {error}{" "}
          <button className="text-link" onClick={onRetry}>
            Повторить обновление
          </button>
        </Notice>
      )}
      <section className="run-stage">
        <div
          className={"run-orbit " + (terminal || cancelling ? "paused" : "")}
          aria-hidden="true"
        >
          <Users size={36} />
          <i />
          <i />
          <i />
        </div>
        {terminal ? (
          <>
            <Notice kind={failed ? "error" : ""}>
              {job?.error || "Не удалось выполнить исследование."}
            </Notice>
            <Button onClick={onBack}>
              <ArrowLeft size={17} />
              Вернуться к настройкам
            </Button>
          </>
        ) : (
          <>
            <h2>
              {!job
                ? "Загружаем состояние запуска…"
                : cancelling
                  ? "Останавливаем исследование"
                  : job.status === "queued"
                    ? "Ждём свободный слот"
                    : "Исследование выполняется"}
            </h2>
            {job && (
              <p>
                {done.toLocaleString("ru-RU")} из{" "}
                {total.toLocaleString("ru-RU")} оценок
              </p>
            )}
            <progress
              max={Math.max(1, total)}
              value={done}
              aria-label="Прогресс симуляции"
            />
            <p className="help">
              {cancelling
                ? "Ждём завершения уже отправленного запроса к модели. Новые оценки не запускаются."
                : "Результат сохранится в архиве. Скорость зависит от модели и размера аудитории."}
            </p>
            <div className="run-actions">
              <Button onClick={onBackground}>Продолжить работу</Button>
              {job && (
                <Button onClick={onCancel} disabled={cancelBusy || cancelling}>
                  <Square size={14} />
                  {cancelBusy || cancelling ? "Останавливаем…" : "Остановить"}
                </Button>
              )}
            </div>
          </>
        )}
      </section>
    </>
  );
}
