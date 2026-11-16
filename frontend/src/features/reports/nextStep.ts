import type { Experiment } from "../../types";
export function nextStep(record: Experiment, pending?: string) {
  if (pending)
    return {
      action: "save",
      title: "Сохраните результат",
      label: "Повторить сохранение",
      detail:
        "Расчёт уже выполнен. Восстановите запись в архив или скачайте JSON перед продолжением.",
    } as const;
  const rows = Object.values(record.report);
  if (
    !rows.length ||
    rows.some(
      (r) =>
        !r.n ||
        Object.entries(record.scenario.population).some(
          ([sid, weight]) => weight > 0 && !r.segments[sid]?.n,
        ),
    )
  )
    return {
      action: "reuse",
      title: "Сначала восстановите покрытие",
      label: "Проверить настройки запуска",
      detail:
        "Валидные ответы получены не у всех предложений или выбранных сегментов. Сравнение и выбор лидера сейчас неполны; проверьте ошибки и настройки модели.",
    } as const;
  if (rows.some((r) => r.failed_n || r.inconsistent_n))
    return {
      action: "reuse",
      title: "Сначала проверьте качество ответов",
      label: "Проверить настройки запуска",
      detail:
        "Есть ошибки или корректировки вероятностей. Разберите предупреждения ниже и подготовьте повторный запуск с однозначным форматом ответа.",
    } as const;
  if (record.mock)
    return {
      action: "validation",
      title: "Пройдите пример проверки",
      label: "Открыть пример живой проверки",
      detail:
        "Демо показывает процесс исследования. Его доли получены по правилам; используйте этот отчёт для знакомства с материалами опроса.",
    } as const;
  if (record.validation)
    return {
      action: "validation",
      title: "Разберите совпадения и расхождения",
      label: "Разобрать расхождения с опросом",
      detail:
        "Ответы загружены. Подлинность и сопоставимость выборки требуют проверки исследователем; сохранение файла само по себе не подтверждает гипотезу.",
    } as const;
  return {
    action: "validation",
    title: "Подготовьте проверку на людях",
    label: "Подготовить живую проверку",
    detail:
      "Симуляция помогает выбрать вопросы и барьеры для исследования. Следующий шаг — подготовить анкету и сопоставить ответы людей с этим снимком.",
  } as const;
}
