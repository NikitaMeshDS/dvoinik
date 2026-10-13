import { ArrowLeft, Users } from "lucide-react";
import { Button, Heading, Notice } from "./components";
import type { Job } from "./types";
export default function JobView({
  job,
  onBack,
}: {
  job: Job | null;
  onBack: () => void;
}) {
  const done = job?.done ?? 0,
    total = job?.total ?? 1,
    failed = job?.status === "failed";
  return (
    <>
      <Heading
        title={
          failed
            ? "Исследование не завершено"
            : "Двойники знакомятся с предложениями"
        }
        description="Прогресс отражает реальные оценки движка."
      />
      <section className="run-stage">
        <div
          className={"run-orbit " + (failed ? "paused" : "")}
          aria-hidden="true"
        >
          <Users size={36} />
          <i />
          <i />
          <i />
        </div>
        {failed ? (
          <>
            <Notice kind="error">
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
              {job?.status === "queued"
                ? "Ждём свободный слот"
                : "Исследование выполняется"}
            </h2>
            <p>
              {done.toLocaleString("ru-RU")} из {total.toLocaleString("ru-RU")}{" "}
              оценок
            </p>
            <progress
              max={Math.max(1, total)}
              value={done}
              aria-label="Прогресс симуляции"
            />
            <p className="help">
              Результат откроется после завершения. Скорость зависит от модели и
              размера аудитории.
            </p>
          </>
        )}
      </section>
    </>
  );
}
