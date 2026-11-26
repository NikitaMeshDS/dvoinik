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
    interrupted = job?.status === "interrupted",
    cancelled = job?.status === "cancelled",
    cancelling = job?.status === "cancelling",
    terminal = failed || cancelled || interrupted;
  return (
    <>
      <Heading
        title={
          interrupted
            ? "Исследование прервано"
            : cancelled
              ? "Исследование остановлено"
              : failed
                ? "Исследование не завершено"
                : "Двойники знакомятся с предложениями"
        }
        description={
          interrupted
            ? "После перезапуска сервиса можно открыть настройки и запустить исследование заново."
            : cancelled
              ? "Частичный результат не сохранён. Можно настроить и запустить новое исследование."
              : failed
                ? "Запуск завершился ошибкой. Проверьте настройки перед новой попыткой."
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
            {job?.request ? (
              <>
                <p className="help">
                  Настройки откроются в черновике. Новая попытка начнётся, когда
                  вы нажмёте кнопку запуска.
                </p>
                <details className="disclosure">
                  <summary>Настройки этого запуска</summary>
                  <div className="disclosure-content">
                    <p>
                      <strong>{job.request.scenario.title}</strong>
                    </p>
                    <p>{job.request.scenario.question}</p>
                    <p>
                      {job.request.mock ? "Демо" : "LLM"} · {job.request.n}{" "}
                      профилей · Seed {job.request.seed} · параллельность{" "}
                      {job.request.concurrency}
                    </p>
                    {Object.entries(job.request.scenario.variants).map(
                      ([variant, text]) => (
                        <p key={variant}>
                          <strong>{variant}:</strong> {text}
                        </p>
                      ),
                    )}
                  </div>
                </details>
              </>
            ) : (
              <p className="help">
                Снимок настроек недоступен для этого задания. Откроется текущий
                черновик; проверьте его перед запуском.
              </p>
            )}
            <Button onClick={onBack}>
              <ArrowLeft size={17} />
              {job?.request
                ? "Восстановить настройки запуска"
                : "Открыть черновик"}
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
