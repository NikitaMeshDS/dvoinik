import { useState } from "react";
import { FlaskConical, Sparkles } from "lucide-react";
import { api } from "../../api";
import { Button, Notice, date, decimal, percent } from "../../components";
import type { Experiment } from "../../types";
import type { Hypotheses as Data, Hypothesis } from "./types";
import { hypothesisChecks, sameHypothesisSetup } from "./hypothesisChecks";
import { hypothesisVerdict } from "./OriginBanner";

const VERDICT = {
  better: "в симуляции выше B",
  same: "оценки симуляции близки",
  worse: "в симуляции выше A",
};

const EVIDENCE_SHOWN = 3;

export default function Hypotheses({
  record,
  data,
  onTest,
  checks = [],
  onOpen,
}: {
  record: Experiment;
  data?: Data;
  onTest?: (hypothesis: Hypothesis, proposal: string) => void;
  checks?: Experiment[];
  onOpen?: (id: string) => void;
}) {
  const [rewritten, setRewritten] = useState<Record<string, string>>({}),
    [busy, setBusy] = useState(""),
    [error, setError] = useState("");
  if (!data) return <p className="help">Готовим гипотезы…</p>;
  const rewrite = async (h: Hypothesis) => {
    setBusy(h.id);
    setError("");
    try {
      const value = await api.request<{ proposal: string }>(
        "/hypotheses/rewrite",
        "POST",
        { record_id: record.id, hypothesis_id: h.id },
      );
      setRewritten((previous) => ({ ...previous, [h.id]: value.proposal }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy("");
    }
  };
  return (
    <section className="hypotheses" aria-labelledby="hypotheses-title">
      <div className="section-heading">
        <h2 id="hypotheses-title">Гипотезы: что поменять в предложении</h2>
        {data.leader && <span>Основа — лидер, вариант {data.leader}</span>}
      </div>
      <p className="help hypotheses-intro">
        Гипотезы построены по частым причинам отказа от лидера и по сегментам,
        где другой вариант сильнее. Порядок — по доле аудитории, которую
        затрагивает причина. Потолок эффекта показывает прирост, если причина
        исчезнет полностью: реальный эффект меньше. Проверка — A/B-запуск «лидер
        против гипотезы», затем живой опрос.
      </p>
      {record.mock && (
        <Notice>
          В демо-режиме новый текст собирается по правилам, а симуляция тоже
          работает на правилах. A/B-запуск покажет работу продукта, а не реакцию
          людей.
        </Notice>
      )}
      {error && <Notice kind="error">{error}</Notice>}
      {!data.items.length ? (
        <p className="hypotheses-empty">
          Частых причин отказа (от 5% сегмента), которые снимаются изменением
          текста, не найдено. Проверьте лидера опросом или добавьте новые
          предложения.
        </p>
      ) : (
        <ol className="hypothesis-list">
          {data.items.map((h) => {
            const proposal = rewritten[h.id] ?? h.proposal,
              extra = h.evidence.length - EVIDENCE_SHOWN;
            return (
              <li key={h.id} className="hypothesis">
                <div className="hypothesis-head">
                  <span className="chip chip-neutral">{h.lever}</span>
                  <span className="hypothesis-ceiling">
                    до +{decimal(h.ceiling_pp)} п.п.
                    <small>потолок в главном сегменте</small>
                  </span>
                </div>
                <h3>{h.change}</h3>
                <p className="hypothesis-segments">
                  {h.segment_names.join(" · ")}
                </p>
                <ul className="hypothesis-evidence">
                  {h.evidence.slice(0, EVIDENCE_SHOWN).map((e) => (
                    <li key={e}>{e}</li>
                  ))}
                </ul>
                {extra > 0 && (
                  <details className="hypothesis-more">
                    <summary>Ещё {extra}</summary>
                    <ul className="hypothesis-evidence">
                      {h.evidence.slice(EVIDENCE_SHOWN).map((e) => (
                        <li key={e}>{e}</li>
                      ))}
                    </ul>
                  </details>
                )}
                {(h.removed.length > 0 || h.added.length > 0) &&
                  !rewritten[h.id] && (
                    <div className="hypothesis-diff">
                      {h.removed.map((t) => (
                        <del key={"-" + t}>{t}</del>
                      ))}
                      {h.added.map((t) => (
                        <ins key={"+" + t}>{t}</ins>
                      ))}
                    </div>
                  )}
                <blockquote className="hypothesis-text">
                  <span>
                    {h.kind === "segment_offer"
                      ? "Текст варианта " + h.alternative
                      : rewritten[h.id]
                        ? "Новый текст · переписан моделью"
                        : "Новый текст · черновик по правилу"}
                  </span>
                  <p>{proposal}</p>
                </blockquote>
                <dl className="hypothesis-metrics">
                  <div>
                    <dt>Сейчас в главном сегменте</dt>
                    <dd>{percent(h.base_rate)}</dd>
                  </div>
                  <div>
                    <dt>Затрагивает аудитории</dt>
                    <dd>{decimal(h.audience_pp)}%</dd>
                  </div>
                  <div>
                    <dt>Живой тест</dt>
                    <dd>
                      {h.check_n
                        ? "≈ " +
                          h.check_n.toLocaleString("ru-RU") +
                          " оценок на вариант"
                        : "эффект слишком мал"}
                    </dd>
                  </div>
                </dl>
                {(() => {
                  const runs = hypothesisChecks(record, h, checks);
                  if (!runs.length) return null;
                  return (
                    <section
                      className="hypothesis-runs"
                      aria-label={"Запуски гипотезы «" + h.change + "»"}
                    >
                      <h4>Связанные запуски: {runs.length}</h4>
                      {runs.map((done) => {
                        const verdict = hypothesisVerdict(done);
                        const same = sameHypothesisSetup(record, h, done);
                        return (
                          <article key={done.id}>
                            <p>
                              {date(done.created_at)} ·{" "}
                              {done.mock ? "Демо" : done.model} · {done.n}{" "}
                              профилей · сегментов:{" "}
                              {
                                Object.values(done.scenario.population).filter(
                                  (w) => w > 0,
                                ).length
                              }
                            </p>
                            <p className="help">
                              {done.scenario.origin?.hypothesis_id
                                ? "Связь по идентификатору гипотезы."
                                : "Старый снимок: связь по сохранённым условиям."}{" "}
                              {same
                                ? "Исходный текст A и состав аудитории сохранены."
                                : "Текст A или состав аудитории изменены. Сверьте условия запуска."}
                            </p>
                            <p>
                              {verdict ? (
                                <>
                                  В симуляции: B — {percent(verdict.b)}, A —{" "}
                                  {percent(verdict.a)}, {VERDICT[verdict.kind]}.
                                </>
                              ) : (
                                "Недостаточно валидных ответов для сравнения A/B."
                              )}
                            </p>
                            <details>
                              <summary>Тексты этого запуска</summary>
                              <dl>
                                <dt>A</dt>
                                <dd>{done.scenario.variants.A}</dd>
                                <dt>B</dt>
                                <dd>{done.scenario.variants.B}</dd>
                              </dl>
                            </details>
                            {onOpen && (
                              <button
                                className="text-link"
                                onClick={() => onOpen(done.id)}
                              >
                                Открыть проверку
                              </button>
                            )}
                          </article>
                        );
                      })}
                      <p className="help">
                        Результаты относятся к этим текстам и параметрам
                        симуляции. Ответы людей и ограничения смотрите в каждом
                        отчёте.
                      </p>
                    </section>
                  );
                })()}
                <div className="hypothesis-actions">
                  {onTest && (
                    <Button kind="primary" onClick={() => onTest(h, proposal)}>
                      <FlaskConical size={16} />
                      Проверить: {h.variant} против гипотезы
                    </Button>
                  )}
                  {!record.mock && h.kind === "objection" && (
                    <Button
                      onClick={() => void rewrite(h)}
                      disabled={busy !== ""}
                    >
                      <Sparkles size={16} />
                      {busy === h.id ? "Переписываем…" : "Переписать моделью"}
                    </Button>
                  )}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
